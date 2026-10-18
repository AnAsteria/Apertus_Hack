"""T08: card fields from supported claims (CONTRACTS section 5, DECISIONS D1).

`card_fields()` builds `Result.fields`: {field: [FieldValue(claim_id, value)]}.
Values are copied by code from the stored claim (or the object entity's name
for relations). Only surfaceable claims appear. A unit's leader or official
contact is shown as such and never as anyone's expertise.
"""
from __future__ import annotations

from ..contracts import Claim, Entity, FieldValue
from .text import ABSENCE_TEXT

# Claim predicate -> card field name. `name` is the card title, not a field.
FIELD_FOR = {
    "role": "role",
    "expertise": "expertise",
    "project": "projects",
    "infrastructure": "infrastructure",
    "service": "services",
    "official_contact": "official_contact",
    "affiliation": "affiliation",
    "member_of": "affiliation",
    "part_of": "part_of",
    "leader": "leads",
    "related_to": "related",
}
# Relations seen from the object's side: a unit's card shows who leads it.
INVERSE_FIELD = {"leader": "led_by", "member_of": "members", "part_of": "includes"}


def card_fields(entity: Entity, claims: list[Claim], entities: dict[str, Entity]) -> dict[str, list[FieldValue]]:
    fields: dict[str, list[FieldValue]] = {}

    def add(name: str, claim: Claim, value: str) -> None:
        bucket = fields.setdefault(name, [])
        if all(fv.value != value for fv in bucket):
            bucket.append(FieldValue(claim_id=claim.claim_id, value=value))

    for c in claims:
        if not c.surfaceable or c.predicate == "name":
            continue
        if c.subject_entity_id == entity.entity_id and c.predicate in FIELD_FOR:
            if c.object_entity_id is not None:
                obj = entities.get(c.object_entity_id)
                if obj is not None:
                    add(FIELD_FOR[c.predicate], c, obj.name)
            elif c.value:
                add(FIELD_FOR[c.predicate], c, c.value)
        elif c.object_entity_id == entity.entity_id and c.predicate in INVERSE_FIELD:
            subj = entities.get(c.subject_entity_id)
            if subj is not None:
                add(INVERSE_FIELD[c.predicate], c, subj.name)
    return fields


def missing_fields(fields: dict[str, list[FieldValue]], wanted: list[str]) -> dict[str, str]:
    """Indexed-corpus absence language for fields a card would normally show."""
    return {f: ABSENCE_TEXT for f in wanted if not fields.get(f)}
