"""T08: entity resolution (architecture step 5).

Merges T07's provisional per-page entities with T06's stub entities and with
each other, keeping every merged-away ID resolvable through `alias_entity_ids`
so existing evidence and T09 v1 references never break.

Merge rules (each is corroborated; a bare name match is never enough):
- A, page anchor: a T07 entity and a T06 stub on the SAME page version with
  the same type and matching names (alias or unique containment).
- B, language variant: the single stub of a type on two pages that T06 linked
  as language variants of each other.
- C, organisations across pages: same type (unit/project/infrastructure/
  service), same name or alias, AND a shared source label or canonical profile.
- D, persons across pages: same title-free full name (at least two tokens)
  AND a shared canonical profile or a shared affiliation/membership target.
  Same-name persons without that are kept apart and reported as possible
  duplicates.

Canonical ID: a stub ID when the cluster has one (stable for T09), else the
smallest ID. Claims are rewritten to canonical IDs; duplicate claims merge
their evidence.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from ..contracts import Claim, Entity, EvidencePair
from ..grounding.text import name_aliases, norm, person_key

AFFILIATION_PREDICATES = frozenset({"affiliation", "member_of", "leader", "part_of"})


@dataclass
class PageInput:
    version_id: str
    document_id: str
    url: str
    source_labels: list[str]
    variant_document_ids: list[str]
    stubs: list[Entity]
    entities: list[Entity]  # T07 provisional entities on this page
    claims: list[Claim]


@dataclass
class ResolutionReport:
    merges: dict[str, int] = field(default_factory=dict)   # rule -> number of unions
    clusters: int = 0
    entities_in: int = 0
    claims_in: int = 0
    claims_out: int = 0
    possible_duplicates: list[list[str]] = field(default_factory=list)  # same-name persons kept apart


class _UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.parent[max(ra, rb)] = min(ra, rb)
        return True


def _match_score(a: str, b: str) -> int:
    """0 = no match; exact alias match scores highest, else the length of the
    longest alias of one name contained in the other (min 4 characters)."""
    aa, bb = name_aliases(a), name_aliases(b)
    if aa & bb:
        return 1000 + max(len(x) for x in aa & bb)
    best = 0
    for x in aa:
        for y in bb:
            short, long_ = sorted((x, y), key=len)
            if len(short) < 4 or short not in long_:
                continue
            # Containment counts only for similar lengths, or when the short name is a whole
            # segment of a "Name - Subtitle" page title: "dbmr" must not match
            # "prize for best dbmr publication", but "spn-005" matches "spn-005 – pilot study".
            segments = {seg.strip() for seg in re.split(r"\s[-–|:]\s", long_)}
            if len(short) / len(long_) >= 0.5 or short in segments:
                best = max(best, len(short))
    return best


def _names_match(a: str, b: str) -> bool:
    return _match_score(a, b) > 0


def resolve(pages: list[PageInput]) -> tuple[list[Entity], list[Claim], ResolutionReport]:
    report = ResolutionReport()
    uf = _UnionFind()
    ents: dict[str, Entity] = {}
    stub_ids: set[str] = set()
    labels: dict[str, set[str]] = defaultdict(set)
    profiles: dict[str, set[str]] = defaultdict(set)
    for p in pages:
        for e in p.stubs + p.entities:
            ents.setdefault(e.entity_id, e)
            uf.find(e.entity_id)
            labels[e.entity_id].update(p.source_labels)
            profiles[e.entity_id].update(e.canonical_profiles)
        stub_ids.update(s.entity_id for s in p.stubs)
    report.entities_in = len(ents)
    report.claims_in = sum(len(p.claims) for p in pages)

    def merge(a: str, b: str, rule: str) -> None:
        if uf.union(a, b):
            report.merges[rule] = report.merges.get(rule, 0) + 1

    # A: T07 entity <-> stub on the same page. A pair merges only when each is the
    # other's unique best match: "DBMR" and "Prize for Best DBMR Publication" do not
    # both attach to one page stub, and equal-score ties merge nothing.
    anchored: dict[str, str] = {}  # entity id -> stub id it was anchored to
    for p in pages:
        scores = {(s.entity_id, e.entity_id): _match_score(s.name, e.name)
                  for s in p.stubs for e in p.entities if s.entity_type == e.entity_type}

        def unique_best(key_index: int, key: str) -> str | None:
            row = [(sc, pair) for pair, sc in scores.items() if pair[key_index] == key and sc > 0]
            if not row:
                return None
            top = max(sc for sc, _ in row)
            winners = [pair for sc, pair in row if sc == top]
            return winners[0][1 - key_index] if len(winners) == 1 else None

        for e in p.entities:
            sid = unique_best(1, e.entity_id)
            if sid and unique_best(0, sid) == e.entity_id:
                anchored[e.entity_id] = sid
                merge(sid, e.entity_id, "A_page_anchor")

    # B: single stub of a type on language-variant pages.
    by_doc = {p.document_id: p for p in pages}
    for p in pages:
        for vdoc in p.variant_document_ids:
            q = by_doc.get(vdoc)
            if q is None:
                continue
            for t in {s.entity_type for s in p.stubs}:
                ps = [s for s in p.stubs if s.entity_type == t]
                qs = [s for s in q.stubs if s.entity_type == t]
                if len(ps) == 1 and len(qs) == 1:
                    merge(ps[0].entity_id, qs[0].entity_id, "B_language_variant")

    # C: organisations with the same name/alias and a shared site or profile.
    orgs = [e for e in ents.values() if e.entity_type != "person"]
    by_alias: dict[tuple[str, str], list[str]] = defaultdict(list)
    for e in orgs:
        for a in name_aliases(e.name):
            if len(a) >= 3:
                by_alias[(e.entity_type, a)].append(e.entity_id)
    for ids in by_alias.values():
        for a, b in zip(ids, ids[1:]):
            if labels[a] & labels[b] or profiles[a] & profiles[b]:
                merge(a, b, "C_org_name_and_site")

    # D: persons with the same full name plus a shared profile or affiliation target.
    targets: dict[str, set[str]] = defaultdict(set)  # person id -> canonical ids of affiliation targets
    for p in pages:
        for c in p.claims:
            if c.predicate in AFFILIATION_PREDICATES and c.object_entity_id:
                targets[c.subject_entity_id].add(c.object_entity_id)
    by_person: dict[str, list[str]] = defaultdict(list)
    for e in ents.values():
        key = person_key(e.name)
        if e.entity_type == "person" and len(key.split()) >= 2:
            by_person[key].append(e.entity_id)
    for ids in by_person.values():
        if len(ids) < 2:
            continue
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                ta = {uf.find(t) for t in targets[a]}
                tb = {uf.find(t) for t in targets[b]}
                if profiles[a] & profiles[b] or ta & tb:
                    merge(a, b, "D_person_name_and_affiliation")
        roots = {uf.find(i) for i in ids}
        if len(roots) > 1:
            report.possible_duplicates.append(sorted(roots))

    # Build clusters and canonical entities.
    clusters: dict[str, list[str]] = defaultdict(list)
    for eid in ents:
        clusters[uf.find(eid)].append(eid)
    canonical: dict[str, str] = {}
    out_entities: dict[str, Entity] = {}
    for members in clusters.values():
        stubs = sorted(m for m in members if m in stub_ids)
        cid = stubs[0] if stubs else min(members)
        for m in members:
            canonical[m] = cid
        base = ents[cid]
        merged_by_anchor = bool(stubs) and len(members) > 1
        # Display name: stubs carry page titles ("Research - Department X"); prefer the
        # longest extracted name that was anchored to a stub of this cluster.
        extracted = [ents[m].name for m in members if m in anchored]
        name = max(extracted, key=len) if extracted else base.name
        out_entities[cid] = base.model_copy(update={
            "name": name,
            "canonical_profiles": sorted(set().union(*(profiles[m] for m in members))),
            "alias_entity_ids": sorted(set(members) - {cid} | set(base.alias_entity_ids)),
            "resolution_state": "confirmed" if merged_by_anchor else base.resolution_state,
            "claim_ids": [], "contact_claim_ids": [], "affiliation_entity_ids": []})
    report.clusters = len(out_entities)

    # Rewrite and deduplicate claims.
    merged: dict[tuple, Claim] = {}
    for p in pages:
        for c in p.claims:
            s = canonical.get(c.subject_entity_id, c.subject_entity_id)
            o = canonical.get(c.object_entity_id, c.object_entity_id) if c.object_entity_id else None
            if o is not None and o == s:
                continue  # relation collapsed by a merge
            key = (s, c.predicate, norm(c.value) if c.value is not None else None, o)
            if key in merged:
                prev = merged[key]
                pairs = {(e.version_id, e.sentence_id) for e in prev.evidence} | \
                        {(e.version_id, e.sentence_id) for e in c.evidence}
                merged[key] = prev.model_copy(update={"evidence": [
                    EvidencePair(version_id=v, sentence_id=sid) for v, sid in sorted(pairs)]})
            else:
                merged[key] = c.model_copy(update={"subject_entity_id": s, "object_entity_id": o})
    claims = list(merged.values())
    report.claims_out = len(claims)
    return list(out_entities.values()), claims, report


def finalize(entities: list[Entity], claims: list[Claim]) -> list[Entity]:
    """Attach claim IDs and supported affiliations to entities after support checking."""
    by_subject: dict[str, list[Claim]] = defaultdict(list)
    for c in claims:
        by_subject[c.subject_entity_id].append(c)
    known = {e.entity_id for e in entities}
    out = []
    for e in entities:
        own = by_subject.get(e.entity_id, [])
        affiliations = sorted({c.object_entity_id for c in own
                               if c.support == "supported" and c.predicate in AFFILIATION_PREDICATES
                               and c.object_entity_id in known and c.object_entity_id != e.entity_id})
        out.append(e.model_copy(update={
            "claim_ids": [c.claim_id for c in own],
            "contact_claim_ids": [c.claim_id for c in own if c.predicate == "official_contact"],
            "affiliation_entity_ids": affiliations}))
    return [Entity.model_validate(x.model_dump()) for x in out]
