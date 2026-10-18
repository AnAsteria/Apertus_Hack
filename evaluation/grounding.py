"""T37: deterministic grounding checks over a built index and over served cards.

Checks (no model, no network):
  * every surfaced field cites claim sentences that exist in the index, in the cited version;
  * former / retired entities never show an official contact;
  * every card quote is byte-identical to the stored sentence of the cited version, with the
    stored URL (served run records, e.g. the T14 HTTP runner output).
Valid citations do not prove semantic support; that is the human-rated sample (`sample`/`support`).

    python -m evaluation.grounding --index-dir <dir> [--run runs/eval.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter


def check_index(entities: dict, resolve) -> dict:
    """`entities`: IndexStore.metadata()[0]; `resolve(sentence_ids)` -> evidence dicts or raises."""
    problems, counts = [], Counter()
    for eid, item in entities.items():
        entity, fields = item['entity'], item.get('fields') or {}
        surfaced = {k: v for k, v in fields.items() if v}
        if surfaced:
            counts['entities_with_fields'] += 1
            counts['field_values'] += sum(len(v) for v in surfaced.values())
            if not item.get('claim_sentence_ids'):
                problems.append({'entity_id': eid, 'problem': 'fields_without_claim_evidence'})
        if entity.get('status') in ('former', 'retired') and surfaced.get('official_contact'):
            problems.append({'entity_id': eid, 'problem': 'former_entity_shows_contact'})
        sids = item.get('claim_sentence_ids') or []
        if sids:
            try:
                got = resolve(sids)
                counts['claim_sentences_checked'] += len(got)
                if len(got) != len(dict.fromkeys(sids)):
                    problems.append({'entity_id': eid, 'problem': 'claim_sentence_missing'})
            except (KeyError, ValueError) as exc:
                problems.append({'entity_id': eid, 'problem': 'claim_sentence_unresolvable:' + type(exc).__name__})
    return {'counts': dict(counts), 'problems': problems}


def check_cards(rows: list[dict], resolve) -> dict:
    """`rows`: run-record rows with served `results`; quotes must equal stored sentences."""
    problems, counts = [], Counter()
    for row in rows:
        for card in row.get('results', []):
            counts['cards'] += 1
            for ev in card.get('evidence', []):
                counts['quotes'] += 1
                try:
                    stored = resolve([ev['sentence_id']])[0]
                except (KeyError, ValueError, IndexError):
                    problems.append({'query_id': row.get('query_id'), 'sentence_id': ev.get('sentence_id'), 'problem': 'quote_unresolvable'})
                    continue
                if stored['version_id'] != ev.get('version_id') or not ev['sentence_id'].startswith(ev.get('version_id', '') + ':'):
                    problems.append({'query_id': row.get('query_id'), 'sentence_id': ev['sentence_id'], 'problem': 'cross_version_reference'})
                elif stored['text'] != ev.get('text'):
                    problems.append({'query_id': row.get('query_id'), 'sentence_id': ev['sentence_id'], 'problem': 'quote_not_identical'})
                elif stored['url'] != ev.get('url'):
                    problems.append({'query_id': row.get('query_id'), 'sentence_id': ev['sentence_id'], 'problem': 'url_mismatch'})
            if card.get('retrieval', {}).get('entity_status') in ('former', 'retired') and (card.get('fields') or {}).get('official_contact'):
                problems.append({'query_id': row.get('query_id'), 'entity_id': card.get('entity_id'), 'problem': 'former_entity_shows_contact'})
    return {'counts': dict(counts), 'problems': problems}


def main(argv=None) -> int:
    from app.storage.indexes import IndexStore, current_generation
    ap = argparse.ArgumentParser(prog='python -m evaluation.grounding')
    ap.add_argument('--index-dir', required=True, help='serving data dir with READY, or a generation dir')
    ap.add_argument('--run', help='T14 run record whose served cards are checked')
    a = ap.parse_args(argv)
    current = current_generation(a.index_dir)
    store = IndexStore(current[0] if current else a.index_dir)
    entities, _ = store.metadata()
    out = {'index': check_index(entities, store.evidence)}
    if a.run:
        with open(a.run, encoding='utf-8') as f:
            out['cards'] = check_cards(json.load(f)['rows'], store.evidence)
    print(json.dumps({k: {'counts': v['counts'], 'n_problems': len(v['problems']), 'problems': v['problems'][:20]} for k, v in out.items()}, indent=1))
    return 1 if any(v['problems'] for v in out.values()) else 0


if __name__ == '__main__':
    sys.exit(main())
