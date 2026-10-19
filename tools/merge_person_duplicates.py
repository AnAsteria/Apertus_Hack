"""EXTRA A6 (#124): merge person entities that are the same person under the same full name.

T08 creates a person entity per page that names them ("Ben Jann" on 4 pages + his own profile
page), so one person's claims are split over several cards. This rewrites entities.jsonl with
alias_entity_ids (the existing T08 mechanism; build.prepare resolves aliases), no other change.

Merge rule (deterministic, no model): same full name after removing titles and word order
("Prof. Dr. Ben Jann" == "Jann, Ben"), at least two name words of 2+ letters, all persons (or a
"<name> (PI)" unit page). The canonical entity is the one with a profile page, else the most
claims. Groups with a retired member or an id already used as an alias elsewhere are left alone.

    python tools/merge_person_duplicates.py IN_KNOWLEDGE_DIR OUT_KNOWLEDGE_DIR [--report merges.json]
"""
import argparse
import collections
import json
import re
import shutil
from pathlib import Path

TITLES = {'prof', 'dr', 'md', 'phd', 'med', 'pd', 'dipl', 'ing', 'msc', 'bsc', 'mba', 'mag', 'pi', 'em',
          'rer', 'nat', 'phil', 'dent', 'vet', 'habil', 'iur', 'lic', 'ma', 'ba'}


def name_key(name):
    words = [w for w in re.findall(r'[^\W\d_]+', name.casefold()) if w not in TITLES]
    return ' '.join(sorted(words)) if len([w for w in words if len(w) >= 2]) >= 2 else None


def merge(entities):
    taken = {a for e in entities for a in e['alias_entity_ids']}
    groups = collections.defaultdict(list)
    for e in entities:
        if e['entity_type'] == 'person' or (e['entity_type'] == 'unit' and e['name'].rstrip().endswith('(PI)')):
            k = name_key(e['name'])
            if k:
                groups[k].append(e)
    merges = []
    for key, members in groups.items():
        if len(members) < 2 or any(m['status'] == 'retired' for m in members):
            continue
        if any(m['entity_id'] in taken for m in members):
            continue
        persons = [m for m in members if m['entity_type'] == 'person'] or members
        canon = max(persons, key=lambda m: (bool(m['canonical_profiles']), len(m['claim_ids']), m['entity_id']))
        others = [m for m in members if m is not canon]
        statuses = {m['status'] for m in members} - {'unknown'}
        if len(statuses) > 1:
            continue  # 'current' vs 'former' disagree: leave for a human
        for m in others:
            canon['alias_entity_ids'] = list(dict.fromkeys(canon['alias_entity_ids'] + [m['entity_id']] + m['alias_entity_ids']))
            canon['claim_ids'] = list(dict.fromkeys(canon['claim_ids'] + m['claim_ids']))
            canon['contact_claim_ids'] = list(dict.fromkeys(canon['contact_claim_ids'] + m['contact_claim_ids']))
            canon['canonical_profiles'] = list(dict.fromkeys(canon['canonical_profiles'] + m['canonical_profiles']))
            canon['affiliation_entity_ids'] = list(dict.fromkeys(canon['affiliation_entity_ids'] + m['affiliation_entity_ids']))
            m['alias_entity_ids'] = []
        if statuses:
            canon['status'] = statuses.pop()
        merges.append({'canonical': canon['entity_id'], 'name': canon['name'],
                       'merged': [(m['entity_id'], m['name']) for m in others], 'claims': len(canon['claim_ids'])})
    return merges


def main():
    p = argparse.ArgumentParser()
    p.add_argument('src'); p.add_argument('dst'); p.add_argument('--report')
    a = p.parse_args()
    src, dst = Path(a.src), Path(a.dst)
    dst.mkdir(parents=True, exist_ok=True)
    entities = [json.loads(l) for l in open(src / 'entities.jsonl', encoding='utf-8')]
    merges = merge(entities)
    with open(dst / 'entities.jsonl', 'w', encoding='utf-8') as f:
        for e in entities:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')
    shutil.copyfile(src / 'claims.jsonl', dst / 'claims.jsonl')
    if a.report:
        Path(a.report).write_text(json.dumps(merges, ensure_ascii=False, indent=1))
    print(json.dumps({'groups_merged': len(merges), 'entities_aliased': sum(len(m['merged']) for m in merges)}))


if __name__ == '__main__':
    main()
