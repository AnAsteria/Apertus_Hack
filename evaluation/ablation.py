"""T20: ablation runner on the T14 gold set and metrics.

Configurations, each producing a T14-compatible run record that `evaluation.report.compute` scores:

  keyword                      BM25 only            (T09 HybridBackend mode="keyword")
  dense                        embeddings only      (mode="dense")
  hybrid                       BM25 + dense, RRF    (mode="hybrid")
  hybrid_expansion             hybrid over the query AND each T18 expanded query, fused by RRF
  hybrid_expansion_assessment  same ranking + T19 assessment, scored separately: assessment never
                               reorders results, so its value is measured as category quality,
                               not as recall (no ranking-only claim, T19)

Runs in-process against a built index directory: no HTTP, no crawling. Latency here is server-side
compute per query, not client latency (that is T14's HTTP runner). Apertus calls (expansion,
assessment) record tokens per query. Interpretations are cached per query text so re-runs cost no
tokens. The evaluation split refuses to run unless the gold set is frozen.

    python -m evaluation.ablation --index-dir <dir> --split development --out-dir evaluation/results/full/dev
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

from . import gold as goldmod
from .report import compute

CONFIGS = ("keyword", "dense", "hybrid", "hybrid_expansion", "hybrid_expansion_assessment")
RRF_K = 60
TOP_K = 10


# Same fusion rule as the served enriched pass (T30), so the ablation measures what is deployed.
from app.search.expansion import rrf_fuse  # noqa: E402


class _InterpretationCache:
    def __init__(self, path: str | None):
        self.path = path
        self.data = {}
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)

    @staticmethod
    def key(text: str, model: str) -> str:
        from app.ai.interpret import INTERPRET_PROMPT_VERSION
        return hashlib.sha256(f"{model}\n{INTERPRET_PROMPT_VERSION}\n{text}".encode()).hexdigest()[:24]

    def get(self, text: str, model: str):
        return self.data.get(self.key(text, model))

    def put(self, text: str, model: str, value: dict) -> None:
        self.data[self.key(text, model)] = value
        if self.path:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)


def _request(text: str, entity_type):
    from app.contracts import SearchRequest
    return SearchRequest(schema_version="1", query=text, revision=1, entity_type=entity_type)


def run_config(config: str, gold: dict, split: str, backends: dict, *, interpret_fn: Callable | None = None,
               assess_fn: Callable | None = None, cache: _InterpretationCache | None = None,
               interpret_model: str = "", corpus_snapshot_id: str | None = None) -> dict:
    """`backends` maps mode -> object with .search(SearchRequest). interpret_fn(text) -> Interpretation;
    assess_fn(query, needs, results) -> (payloads, stats)."""
    mode = "hybrid" if config.startswith("hybrid") else config
    backend = backends[mode]
    rows, tokens = [], []
    for q in gold["queries"]:
        if q["split"] != split:
            continue
        row = {"query_id": q["query_id"], "status": 200, "latency_ms": None, "results": [], "limitations": [],
               "server_timing_ms": None, "error": None, "tokens": None, "expansions": None, "assessment": None}
        t0 = time.perf_counter()
        q_tokens = 0
        try:
            base = backend.search(_request(q["text"], q["requested_type"]))
            results, row["limitations"] = list(base.results), list(base.limitations)
            # Same guard as the served T30 pass: expansion never overrides a refusal or too-broad outcome.
            from app.search.expansion import expansion_allowed
            if config.startswith("hybrid_expansion") and expansion_allowed(getattr(base, "outcome", None)):
                cached = cache.get(q["text"], interpret_model) if cache else None
                if cached is None:
                    interp = interpret_fn(q["text"])
                    cached = {"expanded": [e["text"] for e in interp.expanded_queries],
                              "needs": [n.model_dump() for n in interp.needs],
                              "tokens": interp.usage.prompt_tokens + interp.usage.completion_tokens}
                    q_tokens += cached["tokens"]
                    if cache:
                        cache.put(q["text"], interpret_model, cached)
                row["expansions"] = cached["expanded"]
                lists = [results] + [list(backend.search(_request(t, q["requested_type"])).results)
                                     for t in cached["expanded"]]
                results = rrf_fuse(lists)
                if config.endswith("assessment") and results:
                    from app.contracts import Need
                    needs = [Need(**n) for n in cached["needs"]]
                    payloads, stats = assess_fn(q["text"], needs, results)
                    q_tokens += stats.usage.prompt_tokens + stats.usage.completion_tokens
                    row["assessment"] = {"categories": {p.entity_id: p.category for p in payloads},
                                         "corrections": stats.corrections,
                                         "latency_s": [round(x, 3) for x in stats.latency_s]}
            row["results"] = [r.model_dump() for r in results]
        except Exception as exc:  # recorded as a failed query; never store query text or error text
            row["status"], row["error"], row["results"] = 500, type(exc).__name__, []
        row["latency_ms"] = (time.perf_counter() - t0) * 1000
        row["tokens"] = q_tokens or None
        tokens.append(q_tokens)
        rows.append(row)
    return {"run_id": "run_" + uuid.uuid4().hex, "started_at": datetime.now(timezone.utc).isoformat(),
            "gold_version": gold.get("gold_version"), "gold_hash": goldmod.canonical_hash(gold), "split": split,
            "config": {"name": config, "base_url": None, "notes": "in-process T20 ablation; latency = server compute"},
            "corpus_snapshot_id": corpus_snapshot_id,
            "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
            "tokens_per_query": (sum(tokens) / len(tokens)) if tokens and any(tokens) else None,
            "indexing_time_s": None, "rows": rows}


def assessment_quality(run: dict, gold: dict) -> dict | None:
    """Category quality vs gold, separate from ranking: expected entities should be marked
    direct/related; other returned entities are counted but not called errors (gold is incomplete)."""
    from .metrics import entity_matches
    by_id = {q["query_id"]: q for q in gold["queries"]}
    exp_total = exp_positive = other_total = other_direct = 0
    for row in run["rows"]:
        if not row.get("assessment"):
            continue
        cats = row["assessment"]["categories"]
        for r in row["results"]:
            cat = cats.get(r["entity_id"])
            if cat is None:
                continue
            if any(entity_matches(r, e) for e in by_id[row["query_id"]]["expected"]):
                exp_total += 1
                exp_positive += cat in ("direct_match", "related_capability")
            else:
                other_total += 1
                other_direct += cat == "direct_match"
    if not exp_total and not other_total:
        return None
    return {"expected_marked_direct_or_related": {"rate": exp_positive / exp_total if exp_total else None,
                                                  "n": exp_total},
            "non_expected_marked_direct": {"rate": other_direct / other_total if other_total else None,
                                           "n": other_total,
                                           "note": "gold lists only known answers; not all of these are errors"}}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="T20 ablation runner")
    p.add_argument("--gold", default="evaluation/gold/gold.json")
    p.add_argument("--index-dir", required=True, help="Directory containing the READY search generation")
    p.add_argument("--split", choices=["development", "evaluation"], default="development")
    p.add_argument("--configs", default=",".join(CONFIGS))
    p.add_argument("--out-dir", required=True)
    p.add_argument("--corpus-snapshot")
    a = p.parse_args(argv)
    gold = goldmod.load(a.gold)
    if a.split == "evaluation" and not goldmod.check_frozen(a.gold):
        p.error("evaluation split needs a frozen, unchanged gold set")
    from app.search.backend import HybridBackend
    from app.storage.indexes import current_generation
    directory, _ = current_generation(a.index_dir)
    configs = [c for c in a.configs.split(",") if c]
    modes = {"hybrid" if c.startswith("hybrid") else c for c in configs}
    backends = {m: HybridBackend(directory, mode=m) for m in modes}
    from app.ai.assess import assess
    from app.ai.client import get_client
    from app.ai.interpret import interpret
    client = get_client()
    interpret_model = os.environ.get("BERNMATCH_INTERPRET_MODEL") or client.config.quality_model
    cache = _InterpretationCache(os.path.join(a.out_dir, "interpretations.json"))
    os.makedirs(a.out_dir, exist_ok=True)
    summary = {}
    for c in configs:
        run = run_config(c, gold, a.split, backends, interpret_fn=lambda t: interpret(t, client=client),
                         assess_fn=lambda q, n, r: assess(q, n, r, client=client), cache=cache,
                         interpret_model=interpret_model, corpus_snapshot_id=a.corpus_snapshot)
        with open(os.path.join(a.out_dir, f"run-{a.split}-{c}.json"), "w", encoding="utf-8") as f:
            json.dump(run, f, ensure_ascii=False, indent=1)
        rep = compute(run, gold)
        quality = assessment_quality(run, gold)
        summary[c] = {"recall_at_10": rep["recall_at_k"], "correct_abstention": rep["correct_abstention"],
                      "misleading_avoided": rep["misleading_avoided"], "link_coverage": rep["link_coverage"],
                      "latency_ms": rep["latency_ms"], "tokens_per_query": run["tokens_per_query"],
                      "n_failed": rep["n_failed"], **({"assessment_quality": quality} if quality else {})}
    with open(os.path.join(a.out_dir, f"summary-{a.split}.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
