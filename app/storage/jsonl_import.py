"""Rebuild a corpus database from a T06 JSONL export (`python -m app.ingest export`).

Why: the extraction (T07), entity (T08) and search steps read `corpus.sqlite`, while the file that
travels between people and machines is `corpus.jsonl`. This turns the file back into the database,
in seconds, with the same IDs, so everyone can work on the very same corpus without re-crawling
(a re-crawl changes version IDs).

Restores what those steps read: documents, active versions, sentences, entities, passage-entity
links and source labels. It does NOT restore the page cache, redirect variants or raw responses, so
it is not a way to continue a crawl.
"""
import json
from pathlib import Path

from app.contracts import Document, Entity, Sentence, Version
from .corpus import CorpusStore


def import_jsonl(data_dir, path) -> dict:
    store = CorpusStore(data_dir)  # creates the schema
    counts = {"documents": 0, "sentences": 0, "entities": 0}
    with store.connect() as db, Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            doc = Document.model_validate(row["document"])
            version = Version.model_validate(row["version"])
            db.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?)",
                       (doc.document_id, doc.canonical_url, doc.model_dump_json()))
            db.execute("INSERT OR REPLACE INTO versions VALUES (?,?,?)",
                       (version.version_id, doc.document_id, version.model_dump_json()))
            for raw in row["sentences"]:
                sentence = Sentence.model_validate(raw)
                db.execute("INSERT OR REPLACE INTO sentences VALUES (?,?,?)",
                           (sentence.sentence_id, version.version_id, sentence.model_dump_json()))
                counts["sentences"] += 1
            for raw in row["entities"]:
                entity = Entity.model_validate(raw)
                db.execute("INSERT OR IGNORE INTO entities VALUES (?,?,?)",
                           (entity.entity_id, doc.document_id, entity.model_dump_json()))
                counts["entities"] += 1
            for passage_id, entity_ids in row["passage_entity_ids"].items():
                for entity_id in entity_ids:
                    db.execute("INSERT OR IGNORE INTO passage_entities VALUES (?,?)", (passage_id, entity_id))
            db.execute("INSERT OR REPLACE INTO active_versions VALUES (?,?)", (doc.document_id, version.version_id))
            for label in row["source_labels"]:
                db.execute("INSERT OR IGNORE INTO labels VALUES (?,?)", (doc.document_id, label))
            counts["documents"] += 1
    return counts
