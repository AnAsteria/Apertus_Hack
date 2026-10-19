"""T15 air-gap evidence, run INSIDE the app container (stdlib only):

    docker compose exec -T app python - < scripts/airgap_check.py

1. proves outbound network is blocked (DNS + direct IP connect must both fail);
2. runs unseen queries against the local app and prints outcome, cards, first card, timing and
   the index generation; 3. reports whether the Apertus endpoint configured for the app answers.
Exit 0 only if the network is blocked AND search answered. Paste the output into issue #15."""
import json
import os
import socket
import sys
import time
import urllib.request

QUERIES = sys.argv[1:] or ["Nadelfreie Glukosemessung für Diabetes",
                           "capteurs pour surveiller les ponts en béton",
                           "robot arm for laboratory automation"]


def egress_blocked():
    checks = {}
    try:
        socket.getaddrinfo("huggingface.co", 443)
        checks["dns huggingface.co"] = "RESOLVED"
    except OSError as e:
        checks["dns huggingface.co"] = f"blocked ({type(e).__name__})"
    for ip in ("1.1.1.1", "8.8.8.8"):
        try:
            socket.create_connection((ip, 443), timeout=3).close()
            checks[f"tcp {ip}:443"] = "CONNECTED"
        except OSError as e:
            checks[f"tcp {ip}:443"] = f"blocked ({type(e).__name__})"
    return all(v.startswith("blocked") for v in checks.values()), checks


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main():
    print("time_utc", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    blocked, checks = egress_blocked()
    for k, v in checks.items():
        print(f"{k:24} {v}")
    print("NETWORK BLOCKED" if blocked else "NETWORK REACHABLE - this is NOT an air-gapped run")
    ok = True
    for q in QUERIES:
        t = time.perf_counter()
        try:
            d = post("http://127.0.0.1:7860/api/v1/search",
                     {"schema_version": "1", "query": q, "revision": 1})
        except Exception as e:  # noqa: BLE001
            print(f"query {q!r}: FAILED {type(e).__name__}"); ok = False; continue
        ms = (time.perf_counter() - t) * 1000
        res = d.get("results") or []
        first = res[0] if res else {}
        ev = (first.get("evidence") or [{}])[0]
        print(f"query {q!r}: outcome={d.get('outcome')} cards={len(res)} {ms:.0f} ms "
              f"generation={(first.get('retrieval') or {}).get('generation')}")
        if first:
            print(f"   1. {first.get('display_name')} | {ev.get('url')}")
    base = os.environ.get("APERTUS_BASE_URL", "")
    if os.environ.get("APERTUS_API_KEY"):
        try:
            with urllib.request.urlopen(base + "/models", timeout=10) as r:
                print("apertus endpoint", base, "answers:", r.status)
        except Exception as e:  # noqa: BLE001
            print("apertus endpoint", base, "NOT reachable:", type(e).__name__)
    else:
        print("apertus: off (no APERTUS_API_KEY); search-only run")
    sys.exit(0 if blocked and ok else 1)


main()
