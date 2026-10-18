"""T30: enriched second retrieval pass over T18 expanded queries.

The original query is always searched; each validated expansion is searched with the same
request constraints (entity type, needs). Results are fused at entity level by reciprocal-rank
fusion, the same rule as the T20 ablation (`evaluation/ablation.py` imports `rrf_fuse` from here),
so what is measured is what is served. No LLM call happens here; expansions come from T18.
"""
from __future__ import annotations

import os

RRF_K = 60
TOP_K = 10
MAX_VARIANTS = int(os.environ.get('BERNMATCH_MAX_EXPANSIONS', '4'))


def rrf_fuse(result_lists: list[list], k: int = RRF_K, limit: int = TOP_K, labels: list[str] | None = None) -> list:
    """Entity-level RRF across result lists (one per query variant). The first-seen Result object
    is kept and ranks are renumbered. With `labels`, each kept card records in
    `retrieval.query_variants` which variants found it (traceability, T36)."""
    scores, first, found = {}, {}, {}
    for i, results in enumerate(result_lists):
        for rank, r in enumerate(results, start=1):
            scores[r.entity_id] = scores.get(r.entity_id, 0.0) + 1.0 / (k + rank)
            first.setdefault(r.entity_id, r)
            if labels:
                found.setdefault(r.entity_id, []).append(labels[i])
    ordered = sorted(scores, key=lambda e: (-scores[e], e))[:limit]
    out = []
    for i, e in enumerate(ordered, start=1):
        update = {'rank': i}
        if labels:
            retrieval = dict(first[e].retrieval)
            retrieval['query_variants'] = found[e]
            retrieval['query_variant'] = 'original' if labels[0] in found[e] else 'expansion'
            update['retrieval'] = retrieval
        out.append(first[e].model_copy(update=update))
    return out


def expanded_search(backend, req, expansions: list[str], limit: int = TOP_K):
    """(fused results, used expansion texts). An abstaining or failing variant contributes nothing."""
    texts, seen = [], {req.query.strip().casefold()}
    for text in expansions:
        key = (text or '').strip().casefold()
        if key and key not in seen and len(texts) < MAX_VARIANTS:
            seen.add(key)
            texts.append(text.strip())
    lists = [list(backend.search(req).results)]
    for text in texts:
        try:
            lists.append(list(backend.search(req.model_copy(update={'query': text})).results))
        except Exception:
            lists.append([])
    return rrf_fuse(lists, limit=limit, labels=['original'] + ['expansion: ' + t for t in texts]), texts
