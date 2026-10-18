"""Suppression list: people, pages or entities that must not be ingested or served (T12 policy half).

Pure functions, no I/O beyond reading the JSON file. The ingestion code (T06) should call
`is_suppressed_url` before fetching or storing, and the serving code should call
`is_suppressed_entity` before returning a card. JSON is used, not YAML, so the serving image
needs no extra dependency. Entries hold identifiers only, never the reason in free text about a
person: see docs/data-policy.md.
"""
import json
import unicodedata
from urllib.parse import urlsplit

REASONS = {"removal_request", "former_staff", "inaccurate", "other"}
ACTIONS = {"suppress", "retire"}


def _name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.casefold())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


def norm_url(url: str) -> str:
    p = urlsplit(url.strip())
    return f"{p.netloc.lower().removeprefix('www.')}{p.path.rstrip('/')}" + (f"?{p.query}" if p.query else "")


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    problems = validate(data)
    if problems:
        raise ValueError("invalid suppression list: " + "; ".join(problems[:3]))
    return data


def validate(data: dict) -> list[str]:
    problems = []
    if data.get("schema_version") != "1":
        problems.append("schema_version must be '1'")
    seen = set()
    for e in data.get("entries", []):
        eid = e.get("entry_id", "?")
        if eid in seen:
            problems.append(f"{eid}: duplicate entry_id")
        seen.add(eid)
        if e.get("reason_category") not in REASONS:
            problems.append(f"{eid}: reason_category must be one of {sorted(REASONS)}")
        if e.get("action") not in ACTIONS:
            problems.append(f"{eid}: action must be one of {sorted(ACTIONS)}")
        if not e.get("confirmed_at") or not e.get("confirmed_by_role"):
            problems.append(f"{eid}: needs confirmed_at and confirmed_by_role (verification must be recorded)")
        ids = e.get("identifiers", {})
        if not any(ids.get(k) for k in ("names", "urls", "url_prefixes", "entity_ids")):
            problems.append(f"{eid}: needs at least one identifier")
    return problems


def is_suppressed_url(data: dict, url: str) -> bool:
    """True if the URL equals a listed URL or sits under a listed prefix (same host, path boundary)."""
    u = norm_url(url)
    for e in data.get("entries", []):
        ids = e.get("identifiers", {})
        if any(u == norm_url(x) for x in ids.get("urls", [])):
            return True
        for pre in map(norm_url, ids.get("url_prefixes", [])):
            if u == pre or u.startswith(pre + "/"):
                return True
    return False


def is_suppressed_entity(data: dict, *, entity_id: str | None = None, names: list[str] | None = None,
                         urls: list[str] | None = None) -> bool:
    """True if the entity id, any of its names or any of its profile URLs is listed.
    A name match alone is deliberately enough: suppression errs on the side of removing a card,
    while merging identities on a name alone is forbidden elsewhere."""
    wanted_names = {_name(n) for n in names or []}
    for e in data.get("entries", []):
        ids = e.get("identifiers", {})
        if entity_id and entity_id in ids.get("entity_ids", []):
            return True
        if wanted_names & {_name(n) for n in ids.get("names", [])}:
            return True
        if urls and any(is_suppressed_url({"entries": [e]}, u) for u in urls):
            return True
    return False
