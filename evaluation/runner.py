"""Run the gold queries against a search endpoint and write an immutable run record (T14).

Measures what the client sees (latency including network). Token use and indexing time are not
visible from the search API: they stay null here and T16 fills them from server-side records.
"""
import json
import platform
import sys
import time
import uuid
from datetime import datetime, timezone

import httpx

from . import gold as goldmod

SEARCH_PATH = "/api/v1/search"


def run_gold(gold_path: str, *, split: str, base_url: str | None = None, client: httpx.Client | None = None,
             config_name: str = "default", corpus_snapshot_id: str | None = None, notes: str = "",
             timeout: float = 30.0, enriched: bool = False, enrich_timeout: float = 120.0) -> dict:
    """`client` lets tests pass an in-process ASGI client. Evaluation-split runs need a frozen gold.

    enriched=True measures the full pipeline: the fast results, then the Apertus-enriched ranking
    from the SSE `reranked` event (T30) when the server sends one; otherwise the fast results stay.
    Each row records which list was scored (`scored`), so fast and end-to-end are never mixed."""
    g = goldmod.load(gold_path)
    bad = goldmod.validate(g)
    if bad:
        raise ValueError("gold set invalid: " + "; ".join(bad[:3]))
    if split == "evaluation" and not goldmod.check_frozen(gold_path):
        raise PermissionError("evaluation split needs a frozen, unchanged gold set (run `freeze`)")
    own = client is None
    client = client or httpx.Client(base_url=base_url, timeout=timeout)
    rows = []
    try:
        for q in g["queries"]:
            if q["split"] != split:
                continue
            body = {"schema_version": "1", "query": q["text"], "revision": 1,
                    "entity_type": q["requested_type"], "company_context": None, "needs": [],
                    "enrichment_requested": enriched}
            t0 = time.perf_counter()
            row = {"query_id": q["query_id"], "status": None, "latency_ms": None, "results": [],
                   "limitations": [], "server_timing_ms": None, "error": None}
            try:
                r = client.post(SEARCH_PATH, json=body)
                row["latency_ms"] = (time.perf_counter() - t0) * 1000
                row["status"] = r.status_code
                if r.status_code == 200:
                    data = r.json()
                    row["results"] = data["results"]
                    row["limitations"] = data.get("limitations", [])
                    row["server_timing_ms"] = data.get("timing_ms")
                    row["scored"] = "fast"
                    if enriched and data.get("enrichment_state") == "pending":
                        _enrich(client, data["request_id"], body, row, enrich_timeout, t0)
                else:
                    row["error"] = r.json().get("error", {}).get("code", "HTTP_ERROR")
            except (httpx.HTTPError, ValueError) as exc:
                row["latency_ms"] = (time.perf_counter() - t0) * 1000
                row["error"] = type(exc).__name__  # never store request text or bodies
            rows.append(row)
    finally:
        if own:
            client.close()
    return {"run_id": "run_" + uuid.uuid4().hex, "started_at": datetime.now(timezone.utc).isoformat(),
            "gold_version": g.get("gold_version"), "gold_hash": goldmod.canonical_hash(g), "split": split,
            "config": {"name": config_name, "base_url": base_url, "notes": notes, "enriched": enriched},
            "corpus_snapshot_id": corpus_snapshot_id,
            "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
            "tokens_per_query": None, "indexing_time_s": None, "rows": rows}


def _enrich(client, request_id, body, row, timeout, t0):
    """Follow the enrichment stream; on a `reranked` event score that list instead."""
    try:
        r = client.post(f"{SEARCH_PATH}/{request_id}/enrichment", json=body)
        if r.status_code != 202:
            row["enrichment"] = f"HTTP_{r.status_code}"
            return
        with client.stream("GET", r.json()["events_url"], timeout=timeout) as s:
            kind = None
            for line in s.iter_lines():
                if line.startswith("event: "):
                    kind = line[7:].strip()
                elif line.startswith("data: ") and kind:
                    d = json.loads(line[6:])
                    if kind == "reranked":
                        row["results"] = d["payload"]["results"]
                        row["scored"] = "reranked"
                    elif kind == "error" and not d["payload"].get("retryable", True):
                        row["enrichment"] = d["payload"].get("code")
                    elif kind == "complete":
                        break
        row["end_to_end_ms"] = (time.perf_counter() - t0) * 1000
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        row["enrichment"] = type(exc).__name__


def save(run: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=1)
