"""End-to-end enrichment check: search -> POST enrichment -> SSE stream (T18/T19/T30).

Fictional companies only. Measures client-side time to first cards and to each SSE stage, and
records outcome, interpretation, reranked cards and assessments. Output stays local (cards carry
public contact data from the corpus): write it under data/.

    python tools/enrichment_check.py --base-url http://127.0.0.1:8765 --cases latency --out data/runs/x.json
    python tools/enrichment_check.py --base-url https://kaktamsdengami-bern-match.hf.space --cases profiles --out ...
"""
import argparse
import json
import math
import statistics
import time

import httpx

LATENCY_CASES = [
    ("glucose-en", "partners for a wearable glucose sensor",
     "Fictional startup Zebra Sports (Singapore) builds a wearable glucose sensor for endurance athletes and needs clinical validation in Europe."),
    ("insulin-ai-en", "AI support for insulin dosing decisions",
     "Fictional company DoseWise develops a smartphone app that suggests insulin doses for people with type 1 diabetes."),
    ("oncology-en", "research on why tumours become resistant to therapy",
     "Fictional biotech OncoNova is developing a combination therapy for lung cancer and wants academic partners on resistance mechanisms."),
    ("neuro-robot-en", "robotic tools for brain surgery",
     "Fictional medtech firm MicroNeuro builds miniature robotic instruments for minimally invasive neurosurgery."),
    ("imaging-de", "Bildgebung für Hirntumoren",
     "Das fiktive Start-up NeuroVis entwickelt Software zur MRT-Auswertung bei Hirntumoren und sucht Forschungspartner in Bern."),
    ("cardio-fr", "simulation des flux sanguins dans le cœur",
     "La société fictive CardioSim développe des logiciels de simulation des valves cardiaques et cherche une validation académique."),
    ("sequencing-en", "access to next-generation sequencing for a pilot study",
     "Fictional diagnostics company GeneQuick needs sequencing capacity and bioinformatics support for a 200-sample pilot."),
    ("eye-radio-en", "planning radiation therapy for eye tumours",
     "Fictional software firm OcuPlan builds treatment-planning tools for ocular oncology."),
    ("broad-en", "medtech partners", None),
    ("nofit-en", "antifouling coatings for ship hulls",
     "Fictional company SeaShield develops environmentally friendly antifouling paints for cargo ships."),
]

# B4 (#129): pasted company descriptions, the core use case. Entirely fictional.
PROFILE_CASES = [
    ("profile-diabetes-medtech", "We are looking for research partners for our product.",
     "GlucoTrail AG (fictional) is a 25-person medtech company in Zug. We build a needle-free optical glucose "
     "monitor worn on the wrist for people with type 1 and type 2 diabetes. Our prototype measures glucose "
     "through the skin with near-infrared light and a machine-learning model. In the next 3 years we need a "
     "clinical validation study against continuous glucose monitors, help with insulin-dosing algorithms, and "
     "access to patient cohorts in Switzerland. We want to set up an R&D site in Bern."),
    ("profile-oncology-diagnostics", "Academic partners for a cancer diagnostics test",
     "OncoSight SA (fictional), Lausanne, develops a blood-based liquid-biopsy test that detects early signs of "
     "treatment resistance in lung and breast cancer. We use circulating tumour DNA sequencing and spatial "
     "analysis of tumour biopsies. We are looking for groups working on cancer therapy resistance, tumour "
     "pathology and next-generation sequencing platforms to validate our biomarkers on clinical samples."),
    ("profile-neuro-robotics", "Partners for surgical robotics",
     "NeuroBotics GmbH (fictional), Basel, builds miniature robotic instruments and image guidance for "
     "minimally invasive brain and spine surgery. We need expertise in surgical robotics, medical image "
     "navigation and neurosurgery, plus pre-clinical testing facilities. Long term we want to co-develop "
     "a robot-assisted procedure with a university hospital."),
]


def run_case(client, cid, query, ctx):
    body = {"schema_version": "1", "query": query, "revision": 1, "entity_type": None, "company_context": ctx,
            "needs": [], "enrichment_requested": True}
    t0 = time.perf_counter()
    r = client.post("/api/v1/search", json=body)
    rec = {"case": cid, "query": query, "status": r.status_code, "first_cards_s": round(time.perf_counter() - t0, 3)}
    if r.status_code != 200:
        rec["error"] = r.json().get("error", {}).get("code")
        return rec
    res = r.json()
    rec.update(n_cards=len(res["results"]), outcome=res.get("outcome"), enrichment_state=res["enrichment_state"],
               cards=[{"entity_id": c["entity_id"], "name": c["display_name"], "type": c["entity_type"],
                       "fields": {k: [v["value"] for v in vs] for k, vs in c["fields"].items()},
                       "evidence": [e["text"] for e in c["evidence"][:4]]} for c in res["results"]],
               events=[], t={})
    start = client.post(f"/api/v1/search/{res['request_id']}/enrichment", json=body).json()
    t1 = time.perf_counter()
    ev = None
    with client.stream("GET", start["events_url"], timeout=180) as s:
        for line in s.iter_lines():
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                d = json.loads(line[5:])
                now = round(time.perf_counter() - t1, 3)
                rec["events"].append({"t": now, "type": ev, "payload": d["payload"]})
                key = {"interpretation": "interpretation", "reranked": "reranked", "assessment": "first_assessment",
                       "complete": "complete"}.get(ev)
                if key and key not in rec["t"]:
                    rec["t"][key] = now
                if ev == "complete":
                    break
    return rec


def pct(xs, p):
    xs = sorted(x for x in xs if x is not None)
    return xs[max(0, math.ceil(p / 100 * len(xs)) - 1)] if xs else None


def summary(records):
    out = {}
    for key in ("first_cards", "interpretation", "reranked", "first_assessment", "complete"):
        xs = [r["first_cards_s"] if key == "first_cards" else r.get("t", {}).get(key) for r in records]
        good = [x for x in xs if x is not None]
        out[key] = {"n": len(good), "median": statistics.median(good) if good else None, "p95": pct(xs, 95)}
    errs = {}
    for r in records:
        for e in r.get("events", []):
            if e["type"] == "error":
                errs[e["payload"].get("code")] = errs.get(e["payload"].get("code"), 0) + 1
    out["errors"] = errs
    done = [next((e["payload"] for e in r.get("events", []) if e["type"] == "complete"), {}) for r in records]
    out["assessment_tokens_mean"] = statistics.mean([d.get("prompt_tokens", 0) + d.get("completion_tokens", 0)
                                                     for d in done if d.get("prompt_tokens")] or [0])
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True)
    p.add_argument("--cases", choices=["latency", "profiles"], default="latency")
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    cases = LATENCY_CASES if a.cases == "latency" else PROFILE_CASES
    records = []
    with httpx.Client(base_url=a.base_url, timeout=60) as c:
        for rep in range(a.repeat):
            for case in cases:
                try:
                    rec = run_case(c, *case)
                except Exception as e:
                    rec = {"case": case[0], "error": type(e).__name__, "first_cards_s": None}
                rec["repeat"] = rep
                records.append(rec)
                print(f"{rec['case']:28s} rep={rep} cards={rec.get('n_cards')} outcome={rec.get('outcome')} "
                      f"t={rec.get('t')} errors={[e['payload'].get('code') for e in rec.get('events', []) if e['type'] == 'error']}",
                      flush=True)
    s = summary(records)
    json.dump({"base_url": a.base_url, "cases": a.cases, "summary": s, "records": records},
              open(a.out, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
