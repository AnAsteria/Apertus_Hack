"""T08 runner: T06 corpus + T07 extraction -> resolved entities, checked claims, card fields.

    python -m app.grounding --data-dir data --extraction data/extraction/apertus-v1-5-70b.jsonl

Writes a handoff for T09/T11 under <data-dir>/knowledge/ (git-ignored):
entities.jsonl, claims.jsonl, cards.jsonl ({entity_id, fields}), report.json, and
knowledge.json ({"entities", "claims"}) for `python -m app.search build --knowledge-file`.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import asdict

from ..ai.client import ApertusClient, get_client
from ..contracts import Claim, Entity
from ..entities.resolve import PageInput, finalize, resolve
from .fields import card_fields
from .support import check_claims


def load_pages(data_dir: str, extraction_path: str | None) -> tuple[list[PageInput], "object"]:
    from ..storage.corpus import CorpusStore

    store = CorpusStore(data_dir)
    extracted: dict[str, dict] = {}
    if extraction_path and os.path.exists(extraction_path):
        with open(extraction_path, encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                extracted[row["version_id"]] = row
    pages = []
    for r in store.active_records():
        v, d = r["version"], r["document"]
        x = extracted.get(v.version_id, {})
        pages.append(PageInput(
            version_id=v.version_id, document_id=d.document_id, url=v.url, source_labels=r["source_labels"],
            variant_document_ids=list(d.language_variant_document_ids), stubs=r["entities"],
            entities=[Entity.model_validate(e) for e in x.get("entities", [])],
            claims=[Claim.model_validate(c) for c in x.get("claims", [])]))
    return pages, store


def run(data_dir: str, extraction_path: str | None, *, client: ApertusClient | None = None,
        model: str | None = None, use_judge: bool = True) -> dict:
    t0 = time.perf_counter()
    pages, store = load_pages(data_dir, extraction_path)
    entities, claims, res_report = resolve(pages)
    by_id = {e.entity_id: e for e in entities}

    def lookup(version_id: str, sentence_id: str) -> str | None:
        try:
            return store.get_sentence(version_id, sentence_id).text
        except KeyError:
            return None

    claims, sup_report = check_claims(claims, by_id, lookup, client=client or (get_client() if use_judge else None),
                                      model=model, use_judge=use_judge)
    entities = finalize(entities, claims)
    by_id = {e.entity_id: e for e in entities}
    cards = [{"entity_id": e.entity_id, "fields": {k: [fv.model_dump() for fv in v]
                                                  for k, v in card_fields(e, claims, by_id).items()}}
             for e in entities]

    out_dir = os.path.join(data_dir, "knowledge")
    os.makedirs(out_dir, exist_ok=True)
    for name, rows in (("entities", [e.model_dump() for e in entities]),
                       ("claims", [c.model_dump() for c in claims]), ("cards", cards)):
        with open(os.path.join(out_dir, f"{name}.jsonl"), "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    # T09 handoff: `python -m app.search build --knowledge-file <data-dir>/knowledge/knowledge.json`.
    # All claims are included; the index build keeps only supported ones.
    with open(os.path.join(out_dir, "knowledge.json"), "w", encoding="utf-8") as f:
        json.dump({"entities": [e.model_dump() for e in entities], "claims": [c.model_dump() for c in claims]},
                  f, ensure_ascii=False)
    summary = {
        "pages": len(pages), "entities": len(entities), "claims": len(claims),
        "cards_with_fields": sum(1 for c in cards if c["fields"]),
        "resolution": asdict(res_report), "support": asdict(sup_report),
        "wall_s": round(time.perf_counter() - t0, 2), "out_dir": out_dir,
    }
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return summary


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="T08: resolve entities, check claim support, build card fields")
    p.add_argument("--data-dir", default=os.environ.get("BERNMATCH_DATA_DIR", "data"))
    p.add_argument("--extraction", default=None, help="T07 JSONL (default: newest in <data-dir>/extraction/)")
    p.add_argument("--model", default=None, help="Support-judge model (default: APERTUS_QUALITY_MODEL)")
    p.add_argument("--no-judge", action="store_true", help="Rules only; judge-only claims stay pending")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    path = a.extraction
    if path is None:
        d = os.path.join(a.data_dir, "extraction")
        files = sorted((os.path.join(d, f) for f in os.listdir(d) if f.endswith(".jsonl")), key=os.path.getmtime) \
            if os.path.isdir(d) else []
        path = files[-1] if files else None
    print(json.dumps(run(a.data_dir, path, model=a.model, use_judge=not a.no_judge), indent=2))
    return 0
