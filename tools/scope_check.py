"""T39 (#100) scope-check measurement: interpretation `scope` on a labelled development set.

In-scope: every development-split query of the frozen gold set. Out-of-scope: six nonsense probes
reconstructed from the descriptions in app/search/README.md (the exact probe texts were not stored).

    python tools/scope_check.py --model apertus-v1-5-8b --out data/runs/scope-8b.json
"""
import argparse, json, math, statistics, sys, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, ".")
from app.ai.client import get_client          # noqa: E402
from app.ai.interpret import interpret        # noqa: E402

NONSENSE = ["best pizza delivery in Bern tonight", "show me monkeys", "zeige mir alle Affen",
            "cheap flights to Barcelona in December", "how do I fix the gearbox of my car",
            "Bitcoin price prediction for next week"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--gold", default="evaluation/gold/gold.json")
    p.add_argument("--out", required=True)
    p.add_argument("--split", default="development", choices=["development", "evaluation"])
    p.add_argument("--no-probes", action="store_true")
    a = p.parse_args()
    gold = json.load(open(a.gold))
    # Absent gold queries (e.g. quantum satellites) are research requests: in scope, just not in Bern.
    items = [(q["query_id"], q["text"], "in_scope") for q in gold["queries"] if q["split"] == a.split]
    if not a.no_probes:
        items += [(f"probe-{i}", t, "out_of_scope") for i, t in enumerate(NONSENSE, 1)]
    client = get_client()

    def one(item):
        qid, text, label = item
        t0 = time.perf_counter()
        try:
            r = interpret(text, None, [], client=client, model=a.model)
            return {"id": qid, "label": label, "scope": r.scope, "reason": r.scope_reason,
                    "latency_s": round(time.perf_counter() - t0, 2)}
        except Exception as e:
            return {"id": qid, "label": label, "scope": None, "error": type(e).__name__,
                    "latency_s": round(time.perf_counter() - t0, 2)}

    with ThreadPoolExecutor(4) as pool:
        rows = list(pool.map(one, items))
    lat = sorted(r["latency_s"] for r in rows)
    ok = lambda r: r["scope"] == r["label"]
    inn = [r for r in rows if r["label"] == "in_scope"]
    out = [r for r in rows if r["label"] == "out_of_scope"]
    summary = {"model": a.model, "n": len(rows), "correct": sum(map(ok, rows)),
               "in_scope_kept": sum(r["scope"] == "in_scope" for r in inn), "n_in": len(inn),
               "in_scope_wrongly_refused": [r["id"] for r in inn if r["scope"] == "out_of_scope"],
               "out_of_scope_refused": sum(r["scope"] == "out_of_scope" for r in out), "n_out": len(out),
               "unclear": [r["id"] for r in rows if r["scope"] == "unclear"],
               "errors": [r["id"] for r in rows if r.get("error")],
               "latency_median_s": statistics.median(lat), "latency_p95_s": lat[math.ceil(.95 * len(lat)) - 1]}
    json.dump({"summary": summary, "rows": rows}, open(a.out, "w"), indent=1, ensure_ascii=False)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
