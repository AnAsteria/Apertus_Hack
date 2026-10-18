"""Reuse only public-source vectors with identical text, model and encoder recipe."""
import hashlib
import json
import numpy as np
from app.storage.indexes import IndexStore
from .encoder import digest

RECIPE = 'e5-masked-mean-l2-windows512-stride64-v1'


def text_key(text):
    return hashlib.sha256(text.encode()).hexdigest()


def encode_reusing(texts, encoder, existing=None, progress=None):
    cache, previous = {}, None
    if existing and existing[1]['model']==encoder.manifest and existing[1].get('embedding_recipe','e5-masked-mean-l2-windows512-stride64-v1')==RECIPE:
        directory,manifest=existing
        valid=all(digest(directory/name)==manifest['assets'][name]['sha256']
                  for name in ('search.sqlite','vectors.npy','vector_entries.npy'))
        if valid:
            store=IndexStore(directory)
            entities,entries=store.metadata()
            with store.connect() as db:
                sentences={sid:json.loads(body)['text'] for sid,body in db.execute('SELECT id,body FROM sentences')}
            owners=np.load(directory/'vector_entries.npy',allow_pickle=False)
            previous=np.load(directory/'vectors.npy',mmap_mode='r',allow_pickle=False)
            by_entry={}
            for row,owner in enumerate(owners):
                by_entry.setdefault(int(owner),[]).append(row)
            for i,entry in enumerate(entries):
                if entry['kind']=='passage':
                    text='\n'.join(sentences[sid] for sid in entry['sentence_ids'])
                else:
                    entity=entities[entry['entity_ids'][0]]
                    text=entity['entity']['name']+'\n'+'\n'.join(v['value'] for values in entity['fields'].values() for v in values)
                cache.setdefault(text_key(text),by_entry[i])
    vectors,owners=[],[]
    missing,missing_ids=[],[]
    reused=0
    for i,text in enumerate(texts):
        key=text_key(text)
        if key in cache:
            rows=cache[key]
            vectors.extend(previous[rows])
            owners.extend([i]*len(rows))
            reused+=len(rows)
        else:
            missing.append(text); missing_ids.append(i)
    if missing:
        fresh,mapping=encoder.encode_windows(missing,kind='passage',progress=progress)
        vectors.extend(fresh)
        owners.extend(missing_ids[int(i)] for i in mapping)
    if not vectors:
        return np.empty((0,encoder.dimensions),dtype=np.float32),np.empty(0,dtype=np.int32),reused,len(missing)
    return np.asarray(vectors,dtype=np.float32),np.asarray(owners,dtype=np.int32),reused,len(missing)
