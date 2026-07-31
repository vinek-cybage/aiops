import logging, os

import faiss, numpy as np

from . import config, embeddings

logger = logging.getLogger("orchestrator.faiss_index")


class CaseIndex:
    """Wraps IndexIDMap(IndexFlatIP) so cases.id can be used directly as the FAISS
    vector id — no separate id-translation table needed. Postgres is the source of
    truth; this index is a derived, rebuildable cache."""

    def __init__(self, index):
        self.index = index

    @classmethod
    def load_or_create(cls, path=None):
        path = path or config.FAISS_INDEX_PATH
        if os.path.exists(path):
            try:
                logger.info("Loading FAISS index from %s", path)
                return cls(faiss.read_index(path))
            except Exception:
                # Most likely a truncated/corrupt file from a container killed
                # mid-write (write_index isn't atomic on its own — see save()
                # below, which now writes-then-renames to prevent this for any
                # *future* save, but doesn't help a file already left broken by
                # an old build). Fall through to "start empty" — the caller
                # (poller.main) already rebuilds from Postgres whenever
                # len(index) == 0, so this self-heals instead of crash-looping.
                logger.exception("FAISS index at %s is unreadable — starting empty and rebuilding from DB", path)
        else:
            logger.info("No FAISS index found at %s — starting empty", path)
        return cls(faiss.IndexIDMap(faiss.IndexFlatIP(config.FAISS_DIM)))

    @classmethod
    def rebuild_from_db(cls, conn):
        """Fallback if the index file is missing/corrupt: re-embed every case's
        stored signature_text and re-insert into a fresh index."""
        idx = cls(faiss.IndexIDMap(faiss.IndexFlatIP(config.FAISS_DIM)))
        cur = conn.cursor()
        cur.execute("SELECT id, signature_text FROM cases WHERE signature_text IS NOT NULL")
        rows = cur.fetchall(); cur.close()
        for row in rows:
            vector = embeddings.embed_text(row["signature_text"])
            idx.add(row["id"], vector)
        logger.info("Rebuilt FAISS index from DB: %d vectors", len(rows))
        return idx

    def add(self, case_id, vector):
        self.index.add_with_ids(vector.reshape(1, -1), np.array([case_id], dtype="int64"))

    def search(self, vector, k=5):
        scores, ids = self.index.search(vector.reshape(1, -1), k)
        results = [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != -1]
        return sorted(results, key=lambda pair: pair[1], reverse=True)

    def save(self, path=None):
        # Write to a temp file in the same directory, then atomically rename
        # over the real path — os.replace is a single filesystem operation on
        # POSIX, so a container killed mid-save leaves either the old complete
        # file or the new complete file, never a half-written one.
        path = path or config.FAISS_INDEX_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = f"{path}.tmp-{os.getpid()}"
        faiss.write_index(self.index, tmp_path)
        os.replace(tmp_path, path)

    def __len__(self):
        return self.index.ntotal


class ActionIndex:
    """Same IndexIDMap(IndexFlatIP) wrapper as CaseIndex, but for the small,
    static `actions` catalog — rebuilt in-memory from the DB on every process
    start rather than persisted to disk, since the catalog rarely changes and
    re-embedding ~15 short descriptions is cheap."""

    def __init__(self, index):
        self.index = index

    @classmethod
    def build_from_db(cls, conn):
        from . import db
        idx = cls(faiss.IndexIDMap(faiss.IndexFlatIP(config.FAISS_DIM)))
        for action in db.fetch_all_actions(conn):
            vector = embeddings.embed_text(action["description"])
            idx.index.add_with_ids(vector.reshape(1, -1), np.array([action["id"]], dtype="int64"))
        logger.info("Built action index: %d vectors", len(idx))
        return idx

    def search(self, vector, k):
        scores, ids = self.index.search(vector.reshape(1, -1), k)
        results = [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i != -1]
        return sorted(results, key=lambda pair: pair[1], reverse=True)

    def __len__(self):
        return self.index.ntotal
