"""Model-facing extraction schema for T07 (architecture step 4).

This is what Apertus is asked to return. It is deliberately small and flat so
8B constrained decoding stays reliable:

- Sentences are shown to the model as local numbers [1], [2], ...; the model
  returns those numbers, never quotes. Code maps them to stored sentence IDs.
- Every entity, attribute and relation must cite at least one sentence number.
- Attributes (literal values) and relations (entity to entity) are separate
  lists. A single "fact" with both `value` and `object` let 8B fill both
  (observed live, x1), which code then had to reject.
- Absent information is simply not listed; there are no empty-string fields.

Bump EXTRACTION_SCHEMA_VERSION whenever this file changes: it is part of the
extraction cache key.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EXTRACTION_SCHEMA_VERSION = "x2"

EntityKind = Literal["person", "unit", "project", "infrastructure", "service"]
# Literal-valued predicates. `name` is implied by the entity list; for
# `official_contact` the value is only "email" or "phone" and code reads the contact.
AttributePredicate = Literal["role", "expertise", "project", "infrastructure", "service", "official_contact"]
RelationPredicate = Literal["leader", "member_of", "affiliation", "part_of"]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExtractedEntity(_Closed):
    name: str = Field(min_length=1, max_length=200)
    kind: EntityKind
    sentences: list[int] = Field(min_length=1, max_length=5)


class ExtractedAttribute(_Closed):
    subject: str = Field(min_length=1, max_length=200)
    predicate: AttributePredicate
    value: str = Field(min_length=1, max_length=200)
    sentences: list[int] = Field(min_length=1, max_length=5)


class ExtractedRelation(_Closed):
    subject: str = Field(min_length=1, max_length=200)
    predicate: RelationPredicate
    object: str = Field(min_length=1, max_length=200)
    sentences: list[int] = Field(min_length=1, max_length=5)


class PageExtraction(_Closed):
    entities: list[ExtractedEntity] = Field(max_length=40)
    attributes: list[ExtractedAttribute] = Field(max_length=80)
    relations: list[ExtractedRelation] = Field(max_length=40)
