"""FAISS-backed store of unique error incidents, segregated by service — an
error in payments-service and the identical-looking error in orders-service
are never the same incident, even if their embeddings are near-identical
(see search_same_service). Cross-service similarity is only ever used to
*relate* two incidents (neo4j_store.link_relations), never to merge them.

Only the last MAX_LOGS raw logs are kept per incident (a rolling window, not
full history) — this is what ends up in `latest_logs`/`sample_logs`, kept
small on purpose so a hot incident with thousands of occurrences doesn't
balloon the DB row or the graph node."""

import faiss
import os

MAX_LOGS = int(os.environ.get("MAX_LOGS_PER_INCIDENT", "5"))


class IncidentStore:
    def __init__(self, dim):
        self.index = faiss.IndexFlatIP(dim)
        self.incidents = []  # position == FAISS vector id

    def search_same_service(self, vector, threshold, service):
        """Best match restricted to the same service — the dedup/merge decision."""
        if self.index.ntotal == 0:
            return None
        scores, ids = self.index.search(vector.reshape(1, -1), self.index.ntotal)
        best = None
        for idx, score in zip(ids[0], scores[0]):
            if idx == -1 or self.incidents[idx]["service"] != service:
                continue
            if best is None or score > best[1]:
                best = (int(idx), float(score))
        if best and best[1] >= threshold:
            return best
        return None

    def add(self, incident_id, vector, template, service, log):
        idx = len(self.incidents)
        self.incidents.append({
            "incident_id": incident_id,
            "template": template,
            "service": service,
            "count": 1,
            "logs": [log],
        })
        self.index.add(vector.reshape(1, -1))
        return idx

    def add_log(self, idx, log):
        incident = self.incidents[idx]
        incident["count"] += 1
        incident["logs"].append(log)
        if len(incident["logs"]) > MAX_LOGS:
            del incident["logs"][: len(incident["logs"]) - MAX_LOGS]

    def get(self, idx):
        return self.incidents[idx]

    def vector_for(self, idx):
        return self.index.reconstruct(idx)

    def __len__(self):
        return len(self.incidents)
