"""Pure metric functions for the evaluation harness (T14). No I/O, no model calls.

Definitions are fixed here and in docs/evaluation-protocol.md before any benchmark run.
"""
import math
from urllib.parse import urlsplit


def norm_url(url: str) -> str:
    """Compare URLs ignoring scheme, fragment, a leading 'www.' and a trailing slash."""
    p = urlsplit(url.strip())
    host = p.netloc.lower().removeprefix("www.")
    path = p.path.rstrip("/") or ""
    return f"{host}{path}" + (f"?{p.query}" if p.query else "")


def result_urls(result: dict) -> set[str]:
    return {norm_url(e["url"]) for e in result.get("evidence", []) if e.get("url")}


def entity_matches(result: dict, expected_entity: dict) -> bool:
    """A returned card matches an expected entity when any of its evidence URLs is one of the
    entity's listed URLs (profile page and its language variants, plus explicitly accepted
    equivalents), its TYPE is acceptable, and, when `names` is given, its display name contains
    one of the aliases."""
    wanted = {norm_url(u) for u in expected_entity["urls"]} | {norm_url(u) for u in expected_entity.get("accept_also", [])}
    if not (result_urls(result) & wanted):
        return False
    types = {expected_entity["type"], *expected_entity.get("accept_types", [])}
    if result.get("entity_type") not in types:
        return False
    # Several entities can share one page (two programmes on one URL). `names` then also requires
    # one alias in the card's display name, so a sibling entity on the same page is not a match.
    names = [n.lower() for n in expected_entity.get("names", [])]
    return not names or any(n in result.get("display_name", "").lower() for n in names)


def recall_at_k(results: list[dict], expected: list[dict], k: int = 10) -> float | None:
    """Share of expected entities matched by one of the first k results. None when nothing expected."""
    if not expected:
        return None
    top = results[:k]
    found = sum(1 for e in expected if any(entity_matches(r, e) for r in top))
    return found / len(expected)


def link_coverage(results: list[dict]) -> float | None:
    """Share of returned cards that carry at least one evidence sentence with a source URL.
    This measures presence of links, NOT whether the claims are supported."""
    if not results:
        return None
    return sum(1 for r in results if result_urls(r)) / len(results)


def abstained(results: list[dict]) -> bool:
    return len(results) == 0


def avoided(results: list[dict], avoid: list[dict], k: int = 10) -> bool:
    """True when none of the listed misleading near-matches appears in the first k results."""
    return not any(entity_matches(r, a) for r in results[:k] for a in avoid)


def institutional_exposure(results: list[dict]) -> dict:
    """Share of cards per source host (first evidence URL). Reported, never optimised."""
    hosts = [next(iter(sorted(result_urls(r))), "").split("/")[0] for r in results if result_urls(r)]
    if not hosts:
        return {"shares": {}, "max_share": None}
    shares = {h: hosts.count(h) / len(hosts) for h in sorted(set(hosts))}
    return {"shares": shares, "max_share": max(shares.values())}


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile (p in 0..100). The rule is fixed so p95 is reproducible."""
    if not values:
        return None
    s = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(s)))
    return s[rank - 1]


def median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def field_completeness(results: list[dict], fields: tuple[str, ...]) -> dict:
    """Per field: share of cards where the field has at least one supported value.
    Completeness only; accuracy needs human adjudication."""
    if not results:
        return {f: None for f in fields}
    return {f: sum(1 for r in results if r.get("fields", {}).get(f)) / len(results) for f in fields}


def support_rate(ratings: list[str]) -> dict:
    """From adjudicated samples ('supported'|'partly'|'unsupported'). Always report n."""
    n = len(ratings)
    if n == 0:
        return {"n": 0, "supported": None, "partly": None, "unsupported": None}
    return {"n": n, **{k: ratings.count(k) / n for k in ("supported", "partly", "unsupported")}}
