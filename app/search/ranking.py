"""Max per entity BEFORE rank fusion: duplicate passages cannot add votes."""
import numpy as np


def entity_max(scores, entries, allowed):
    best = {}
    for index,score in scores:
        for eid in entries[index]['entity_ids']:
            if eid not in allowed:
                continue
            old = best.get(eid)
            if old is None or score > old[0] or (score == old[0] and index < old[1]):
                best[eid] = (float(score),int(index))
    return best


def reciprocal_rank_fusion(channels, constant=60, depth=100):
    scores = {}
    for channel in channels:
        ranked = sorted(channel,key=lambda eid:(-channel[eid][0],eid))[:depth]
        for rank,eid in enumerate(ranked,1):
            scores[eid] = scores.get(eid,0.) + 1/(constant+rank)
    return scores


def diversify(scores, representatives, limit=10, relevance_weight=.85):
    """MMR over relevance-normalized scores. No institutional quotas."""
    if not scores:
        return []
    scale = max(scores.values())
    # No cut-off on the fused score: under RRF an entity ranked first by both
    # channels scores 2/61, while every single-channel candidate scores at most
    # 1/61, so a "half the best" cut-off left one card. Candidates are already
    # bounded by each channel's depth and the dense similarity threshold.
    remaining = set(scores)
    selected = []
    while remaining and len(selected) < limit:
        def criterion(eid):
            redundancy = max((float(np.dot(representatives[eid],representatives[other])) for other in selected),default=0.)
            return relevance_weight*scores[eid]/scale-(1-relevance_weight)*max(0.,redundancy)
        winner = min(remaining,key=lambda eid:(-criterion(eid),-scores[eid],eid))
        selected.append(winner); remaining.remove(winner)
    return selected
