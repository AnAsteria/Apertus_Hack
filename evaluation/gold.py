"""Gold-set schema, validation and freezing (T14).

Expected entities are identified by canonical source URLs because production entity IDs only
exist after T06/T08 run. Freezing records a hash of the query content; benchmark runs on the
evaluation split refuse to start if the gold file no longer matches its frozen hash.
"""
import hashlib
import json
import os

CATEGORIES = {"professional", "lay", "synonym", "cross_lingual", "partial", "absent", "misleading",
              "person_unit", "contact_freshness"}
LANGS = {"en", "de", "fr", "it", "ru"}
TYPES = {"person", "unit", "project", "infrastructure", "service"}
FROZEN_NAME = "FROZEN.json"


def canonical_hash(gold: dict) -> str:
    """Hash of the queries only, so editing notes or status does not change it."""
    body = json.dumps(gold["queries"], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate(gold: dict, final: bool = False) -> list[str]:
    """Return a list of problems (empty = valid). `final` adds the 30-50 query size check."""
    problems: list[str] = []
    qs = gold.get("queries", [])
    ids = [q.get("query_id") for q in qs]
    if len(ids) != len(set(ids)):
        problems.append("duplicate query_id")
    split_by_group: dict[str, set] = {}
    for q in qs:
        qid = q.get("query_id", "?")
        for key in ("query_id", "intent_group_id", "split", "text", "language", "requested_type", "category"):
            if not q.get(key):
                problems.append(f"{qid}: missing {key}")
        if q.get("split") not in ("development", "evaluation"):
            problems.append(f"{qid}: split must be development|evaluation")
        if q.get("language") not in LANGS:
            problems.append(f"{qid}: language not in {sorted(LANGS)}")
        if q.get("requested_type") not in TYPES:
            problems.append(f"{qid}: requested_type invalid")
        if q.get("category") not in CATEGORIES:
            problems.append(f"{qid}: category invalid")
        split_by_group.setdefault(q.get("intent_group_id"), set()).add(q.get("split"))
        absent = q.get("category") == "absent"
        if absent and q.get("expected"):
            problems.append(f"{qid}: absent query must not list expected entities")
        if not absent and not q.get("expected"):
            problems.append(f"{qid}: needs at least one expected entity (or category absent)")
        for e in q.get("expected", []):
            if not e.get("urls") or e.get("type") not in TYPES:
                problems.append(f"{qid}: expected entity needs urls and a valid type")
        if not q.get("provenance"):
            problems.append(f"{qid}: missing provenance (source URL + note)")
    for g, splits in split_by_group.items():
        if len(splits) > 1:
            problems.append(f"intent group {g} is split across partitions (paraphrase leakage)")
    if final and not 30 <= len(qs) <= 50:
        problems.append(f"final gold needs 30-50 queries, has {len(qs)}")
    return problems


def freeze(gold_path: str, out_dir: str | None = None) -> dict:
    gold = load(gold_path)
    bad = validate(gold)
    if bad:
        raise ValueError("cannot freeze an invalid gold set: " + "; ".join(bad[:5]))
    rec = {"gold_version": gold.get("gold_version"), "gold_hash": canonical_hash(gold), "n_queries": len(gold["queries"])}
    with open(os.path.join(out_dir or os.path.dirname(gold_path), FROZEN_NAME), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=1)
    return rec


def check_frozen(gold_path: str) -> bool:
    frozen = os.path.join(os.path.dirname(gold_path), FROZEN_NAME)
    if not os.path.exists(frozen):
        return False
    with open(frozen, encoding="utf-8") as f:
        return json.load(f)["gold_hash"] == canonical_hash(load(gold_path))
