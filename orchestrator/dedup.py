from collections import namedtuple

from . import config, embeddings
from .grouping import build_signature_text

DedupDecision = namedtuple("DedupDecision", ["is_duplicate", "matched_case_id", "score", "vector", "signature_text"])


def decide(group, index, candidate_cases):
    """candidate_cases: rows for this group's service already filtered by the caller
    to status IN ('OPEN','INVESTIGATING') and updated_at within RECURRENCE_LOOKBACK_SECONDS
    (see db.fetch_recent_open_cases). This function only decides duplicate vs new."""
    signature_text = build_signature_text(group)
    vector = embeddings.embed_text(signature_text)

    candidate_ids = {c["id"] for c in candidate_cases}
    best_score = None

    if candidate_ids and len(index) > 0:
        results = index.search(vector, k=min(5, len(index)))
        for case_id, score in results:
            if case_id in candidate_ids:
                best_score = score
                break

    if best_score is not None and best_score >= config.SIMILARITY_THRESHOLD:
        return DedupDecision(True, matched_case_id=case_id, score=best_score,
                              vector=vector, signature_text=signature_text)

    return DedupDecision(False, matched_case_id=None, score=best_score,
                          vector=vector, signature_text=signature_text)
