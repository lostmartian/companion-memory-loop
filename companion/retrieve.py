from companion import config, vectors
from companion.store import Store

FTS_BASE_SCORE = 0.6
RECENCY_WEIGHT = 0.1


def _score_candidates(
    store: Store,
    vector_hits: list[tuple[int, float]],
    fts_hits: list,
) -> list[tuple[object, float]]:
    all_active = store.get_active()
    max_id = max((r["id"] for r in all_active), default=1)

    scores: dict[int, float] = {}
    for fact_id, distance in vector_hits:
        scores[fact_id] = scores.get(fact_id, 0.0) + (1.0 - distance)
    for rank, row in enumerate(fts_hits):
        scores[row["id"]] = scores.get(row["id"], 0.0) + (
            FTS_BASE_SCORE - 0.05 * rank
        )

    results = []
    for fact_id, score in scores.items():
        row = store.get_fact(fact_id)
        if row is None or row["status"] != "active":
            continue
        recency = RECENCY_WEIGHT * (fact_id / max_id)
        results.append((row, round(score + recency, 4)))

    results.sort(key=lambda pair: pair[1], reverse=True)
    return results


def retrieve(store: Store, query_text: str, k: int | None = None) -> list[tuple[object, float]]:
    k = k or config.RETRIEVAL_TOP_K
    try:
        vector_hits = vectors.query_similar(query_text, k=k * 2)
    except Exception:
        vector_hits = []
    fts_hits = store.search_fts(query_text, limit=k * 2)
    ranked = _score_candidates(store, vector_hits, fts_hits)
    return ranked[:k]
