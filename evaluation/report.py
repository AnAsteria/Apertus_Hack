"""Turn a run record plus its gold set into metrics and a human-adjudication sheet (T14)."""
import csv
import random

from . import metrics as m
from .gold import canonical_hash

FIELDS = ("affiliation", "expertise", "contact", "projects", "infrastructure")


def compute(run: dict, gold: dict, k: int = 10) -> dict:
    if run["gold_hash"] != canonical_hash(gold):
        raise ValueError("run record does not belong to this gold file (hash mismatch)")
    by_id = {q["query_id"]: q for q in gold["queries"]}
    recalls, per_cat, abst, avoid_ok, lat, cards = [], {}, [], [], [], []
    errors = 0
    for row in run["rows"]:
        q = by_id[row["query_id"]]
        if row["status"] != 200:
            errors += 1  # failed queries count against recall and abstention below
        res = row["results"]
        if row["latency_ms"] is not None:
            lat.append(row["latency_ms"])
        cards += res
        if q["category"] == "absent":
            abst.append(m.abstained(res) and row["status"] == 200)
        else:
            r = m.recall_at_k(res, q["expected"], k)
            recalls.append(r)
            per_cat.setdefault(q["category"], []).append(r)
        if q.get("avoid"):
            avoid_ok.append(m.avoided(res, q["avoid"], k))

    def mean(xs):
        return sum(xs) / len(xs) if xs else None

    return {
        "run_id": run["run_id"], "split": run["split"], "gold_version": run["gold_version"], "k": k,
        "n_queries": len(run["rows"]), "n_failed": errors,
        "recall_at_k": {"mean": mean(recalls), "n": len(recalls),
                        "by_category": {c: {"mean": mean(v), "n": len(v)} for c, v in sorted(per_cat.items())}},
        "link_coverage": m.link_coverage(cards), "n_cards": len(cards),
        "correct_abstention": {"rate": mean([float(a) for a in abst]), "n": len(abst)},
        "misleading_avoided": {"rate": mean([float(a) for a in avoid_ok]), "n": len(avoid_ok)},
        "institutional_exposure": m.institutional_exposure(cards),
        "field_completeness": m.field_completeness(cards, FIELDS),
        "latency_ms": {"median": m.median(lat), "p95": m.percentile(lat, 95), "n": len(lat)},
        "tokens_per_query": run.get("tokens_per_query"), "indexing_time_s": run.get("indexing_time_s"),
        "not_measured_here": ["evidence support (needs the adjudicated sheet)", "field accuracy (needs adjudication)",
                              "tokens/query and indexing time (server-side records, T16)"],
    }


def write_sample_sheet(run: dict, path: str, n: int = 40, seed: int = 20261018) -> int:
    """Random sample of returned cards for a human to rate support. The seed is fixed so the
    sample is reproducible. Raters fill the `rating` column: supported|partly|unsupported."""
    cards = [(row["query_id"], r) for row in run["rows"] for r in row["results"]]
    random.Random(seed).shuffle(cards)
    sample = sorted(cards[:n], key=lambda c: (c[0], c[1]["rank"]))
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["query_id", "rank", "display_name", "reason", "evidence_text", "evidence_url", "rating", "note"])
        for qid, r in sample:
            ev = r["evidence"][0]
            w.writerow([qid, r["rank"], r["display_name"], r["reason"], ev["text"], ev["url"], "", ""])
    return len(sample)


def support_from_sheet(path: str) -> dict:
    with open(path, encoding="utf-8", newline="") as f:
        ratings = [row["rating"].strip().lower() for row in csv.DictReader(f) if row["rating"].strip()]
    bad = [r for r in ratings if r not in ("supported", "partly", "unsupported")]
    if bad:
        raise ValueError(f"unknown ratings: {sorted(set(bad))}")
    return m.support_rate(ratings)
