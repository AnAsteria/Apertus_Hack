"""Operator-only indexing of stored records; queries never call this module."""
import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from pathlib import Path
import numpy as np
from app.contracts import Claim, Entity
from app.storage.indexes import INDEX_VERSION, current_generation
from .analysis import analyze
from .encoder import digest


def prepare(records, extra_entities=(), claims=()):
    versions, sentences, entities = {}, {}, {}
    for record in records:
        version = record['version']
        if version.state != 'active':
            continue
        versions[version.version_id] = version
        for sentence in record['sentences']:
            if sentence.version_id != version.version_id:
                raise ValueError('cross_version_sentence')
            sentences[sentence.sentence_id] = sentence
        for entity in record['entities']:
            entities[entity.entity_id] = entity
    # Explicit T08 payloads use the existing Entity/Claim models. No name-only
    # merging or model-authored quotations. No resolved payload is presumed.
    for entity in extra_entities:
        entity = Entity.model_validate(entity)
        entities[entity.entity_id] = entity
    aliases = {}
    for eid, entity in entities.items():
        for alias in entity.alias_entity_ids:
            if alias in aliases and aliases[alias] != eid:
                raise ValueError('conflicting_alias')
            aliases[alias] = eid
    def canonical(eid):
        seen = set()
        while eid in aliases:
            if eid in seen:
                raise ValueError('alias_cycle')
            seen.add(eid); eid = aliases[eid]
        entity = entities.get(eid)
        return eid if entity and entity.status != 'retired' else None
    for alias in aliases:
        canonical(alias)
    fields, claim_refs = {}, {}
    for raw in claims:
        claim = Claim.model_validate(raw)
        eid = canonical(claim.subject_entity_id)
        if eid is None:
            continue
        entity = entities[eid]
        if claim.claim_id not in entity.claim_ids:
            raise ValueError('undeclared_entity_claim')
        for evidence in claim.evidence:
            sentence = sentences.get(evidence.sentence_id)
            if sentence is None or sentence.version_id != evidence.version_id:
                raise ValueError('unavailable_claim_evidence')
        # Qualified claims are withheld until their qualification can be shown
        # by the shared UI; presence of a valid citation is not support proof.
        if claim.support != 'supported':
            continue
        if claim.predicate == 'official_contact' and entity.status != 'current':
            continue
        value = claim.value
        if claim.object_entity_id:
            target = canonical(claim.object_entity_id)
            if not target:
                raise ValueError('unavailable_claim_object')
            value = entities[target].name
        fields.setdefault(eid,{}).setdefault(claim.predicate,[]).append({'claim_id':claim.claim_id,'value':value})
        claim_refs.setdefault(eid,[]).extend(e.sentence_id for e in claim.evidence)
    entries, texts, first_evidence = [], [], {}
    for record in records:
        version = record['version']
        if version.version_id not in versions:
            continue
        for passage in version.passages:
            eids = sorted({x for old in record['passage_entity_ids'].get(passage.passage_id,[]) if (x:=canonical(old))})
            if not eids:
                continue
            if any(s not in sentences or sentences[s].passage_id != passage.passage_id for s in passage.sentence_ids):
                raise ValueError('unavailable_passage_sentence')
            entries.append({'kind':'passage','language':version.language,'sentence_ids':passage.sentence_ids,'entity_ids':eids})
            texts.append('\n'.join(sentences[s].text for s in passage.sentence_ids))
            for eid in eids:
                first_evidence.setdefault(eid,passage.sentence_ids)
    retained = {}
    for eid in sorted(entities):
        if canonical(eid) != eid or eid not in first_evidence:
            continue
        entity = entities[eid]
        refs = list(dict.fromkeys(claim_refs.get(eid,[]) or first_evidence[eid]))
        profile = entity.name+'\n'+'\n'.join(v['value'] for values in fields.get(eid,{}).values() for v in values)
        language = versions[sentences[refs[0]].version_id].language
        entries.append({'kind':'profile','language':language,'sentence_ids':refs,'entity_ids':[eid]})
        texts.append(profile)
        retained[eid] = {'entity':entity.model_dump(),'fields':fields.get(eid,{}),'claim_sentence_ids':list(dict.fromkeys(claim_refs.get(eid,[])))}
    return versions,sentences,retained,entries,texts


def build_index(records, data_dir, encoder, *, extra_entities=(), claims=(), progress=None):
    started = time.perf_counter()
    versions,sentences,entities,entries,texts = prepare(records,extra_entities,claims)
    payload = {'index_version':INDEX_VERSION,'model':encoder.manifest,'versions':sorted(versions),
               'entities':entities,'entries':entries,'texts_sha256':hashlib.sha256('\n'.join(texts).encode()).hexdigest()}
    fingerprint = hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    existing = current_generation(data_dir)
    if existing and existing[1]['fingerprint'] == fingerprint:
        # Verify persisted assets before declaring reuse. Do not run the encoder.
        for name, expected in existing[1]['assets'].items():
            if digest(existing[0]/name) != expected['sha256']:
                raise ValueError('existing_index_hash_mismatch')
        return existing[1] | {'reused':True}
    root = Path(data_dir)
    parent = root/'indexes'; parent.mkdir(parents=True,exist_ok=True)
    name = uuid.uuid4().hex
    stage = parent/('.'+name+'.building'); stage.mkdir()
    try:
        with sqlite3.connect(stage/'search.sqlite') as db:
            db.executescript('''
                CREATE TABLE versions (id TEXT PRIMARY KEY,body TEXT NOT NULL);
                CREATE TABLE sentences (id TEXT PRIMARY KEY,version_id TEXT NOT NULL,body TEXT NOT NULL);
                CREATE TABLE entities (id TEXT PRIMARY KEY,body TEXT NOT NULL);
                CREATE TABLE entries (id INTEGER PRIMARY KEY,body TEXT NOT NULL);
                CREATE VIRTUAL TABLE keyword USING fts5(tokens, content='');
            ''')
            db.executemany('INSERT INTO versions VALUES (?,?)',[(k,v.model_dump_json()) for k,v in versions.items()])
            db.executemany('INSERT INTO sentences VALUES (?,?,?)',[(k,v.version_id,v.model_dump_json()) for k,v in sentences.items()])
            db.executemany('INSERT INTO entities VALUES (?,?)',[(k,json.dumps(v)) for k,v in entities.items()])
            for i,(entry,text) in enumerate(zip(entries,texts)):
                db.execute('INSERT INTO entries VALUES (?,?)',(i,json.dumps(entry)))
                db.execute('INSERT INTO keyword(rowid,tokens) VALUES (?,?)',(i+1,' '.join(analyze(text,entry['language']))))
            db.execute("INSERT INTO keyword(keyword) VALUES ('optimize')")
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            db.commit()
            db.execute('VACUUM')
        vectors,owners = encoder.encode_windows(texts,kind='passage',progress=progress)
        vectors = np.asarray(vectors,dtype=np.float32)
        owners = np.asarray(owners,dtype=np.int32)
        if vectors.ndim != 2 or vectors.shape[0] != len(owners) or not np.isfinite(vectors).all():
            raise ValueError('invalid_dense_arrays')
        if set(owners.tolist()) != set(range(len(entries))):
            raise ValueError('missing_entry_vectors')
        if not np.allclose(np.linalg.norm(vectors,axis=1),1,atol=1e-4):
            raise ValueError('unnormalized_vectors')
        np.save(stage/'vectors.npy',vectors,allow_pickle=False)
        np.save(stage/'vector_entries.npy',owners,allow_pickle=False)
        shutil.copytree(encoder.root,stage/'model')
        assets = {str(p.relative_to(stage)):{'bytes':p.stat().st_size,'sha256':digest(p)}
                  for p in sorted(stage.rglob('*')) if p.is_file()}
        manifest = {'index_version':INDEX_VERSION,'fingerprint':fingerprint,'generation':name,
                    'model':encoder.manifest,'counts':{'versions':len(versions),'sentences':len(sentences),
                    'entities':len(entities),'entries':len(entries),'passage_entries':sum(e['kind']=='passage' for e in entries),
                    'profile_entries':sum(e['kind']=='profile' for e in entries),'vectors':len(vectors),'dimensions':vectors.shape[1]},
                    'assets':assets,'asset_bytes':sum(p['bytes'] for p in assets.values()),
                    'build_seconds':time.perf_counter()-started,'reused':False}
        (stage/'manifest.json').write_text(json.dumps(manifest,indent=2))
        final = parent/name
        os.replace(stage,final)
        marker = root/('READY.'+name+'.tmp')
        marker.write_text(json.dumps({'generation':name,'fingerprint':fingerprint}))
        os.replace(marker,root/'READY')
        return manifest
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True)
        raise
