"""CLI: python -m evaluation validate|freeze|run|report|sample|support  (see docs/evaluation-protocol.md)."""
import argparse
import json
import sys

from . import gold, report, runner

DEFAULT_GOLD = "evaluation/gold/gold.json"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evaluation")
    ap.add_argument("--gold", default=DEFAULT_GOLD)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--final", action="store_true", help="also require 30-50 queries")
    sub.add_parser("freeze")
    r = sub.add_parser("run")
    r.add_argument("--base-url", required=True)
    r.add_argument("--split", choices=["development", "evaluation"], required=True)
    r.add_argument("--config", default="default")
    r.add_argument("--corpus-snapshot", default=None)
    r.add_argument("--out", required=True)
    rp = sub.add_parser("report")
    rp.add_argument("run")
    sm = sub.add_parser("sample")
    sm.add_argument("run")
    sm.add_argument("--out", required=True)
    sm.add_argument("-n", type=int, default=40)
    su = sub.add_parser("support")
    su.add_argument("sheet")
    a = ap.parse_args(argv)

    if a.cmd == "validate":
        problems = gold.validate(gold.load(a.gold), final=a.final)
        print("\n".join(problems) or "gold set valid")
        return 1 if problems else 0
    if a.cmd == "freeze":
        print(json.dumps(gold.freeze(a.gold), indent=1))
    elif a.cmd == "run":
        run = runner.run_gold(a.gold, split=a.split, base_url=a.base_url, config_name=a.config,
                              corpus_snapshot_id=a.corpus_snapshot)
        runner.save(run, a.out)
        print(f"wrote {a.out}: {len(run['rows'])} queries")
    elif a.cmd == "report":
        run = json.load(open(a.run, encoding="utf-8"))
        print(json.dumps(report.compute(run, gold.load(a.gold)), indent=1))
    elif a.cmd == "sample":
        run = json.load(open(a.run, encoding="utf-8"))
        print(f"wrote {report.write_sample_sheet(run, a.out, a.n)} cards to {a.out}")
    elif a.cmd == "support":
        print(json.dumps(report.support_from_sheet(a.sheet), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
