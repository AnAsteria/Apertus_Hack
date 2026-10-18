"""Atomic, versioned local search bundles; runtime opens a read-only snapshot.

No pickle, network, crawl or model endpoint. READY is published only after hashes,
SQLite and dense arrays have been validated. Prior generations remain intact.
"""
import json
import re
import sqlite3
from pathlib import Path

INDEX_VERSION = 1


def current_generation(data_dir):
    root = Path(data_dir)
    try:
        marker = json.loads((root/'READY').read_text())
        name = marker['generation']
        if not re.fullmatch('[a-f0-9]{32}', name):
            return None
        path = root/'indexes'/name
        manifest = json.loads((path/'manifest.json').read_text())
        if manifest['index_version'] != INDEX_VERSION or marker['fingerprint'] != manifest['fingerprint']:
            return None
        return path, manifest
    except (OSError, ValueError, KeyError, TypeError):
        return None


class IndexStore:
    def __init__(self, directory):
        self.root = Path(directory)
        self.path = self.root/'search.sqlite'

    def connect(self):
        return sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro&immutable=1', uri=True)

    def metadata(self):
        with self.connect() as db:
            entities = {eid:json.loads(body) for eid,body in db.execute('SELECT id,body FROM entities')}
            entries = [json.loads(body) for (body,) in db.execute('SELECT body FROM entries ORDER BY id')]
        return entities,entries

    def keyword(self, expression):
        if not expression:
            return []
        with self.connect() as db:
            return db.execute('SELECT rowid-1,-bm25(keyword) FROM keyword WHERE keyword MATCH ?',
                              (expression,)).fetchall()

    def evidence(self, sentence_ids):
        with self.connect() as db:
            result = []
            for sid in dict.fromkeys(sentence_ids):
                row = db.execute('SELECT s.id,s.version_id,s.body,v.body FROM sentences s JOIN versions v '
                                 'ON s.version_id=v.id WHERE s.id=?',(sid,)).fetchone()
                if row is None:
                    raise KeyError('evidence_unavailable')
                sid,vid,sentence_body,version_body = row
                sentence,version = json.loads(sentence_body),json.loads(version_body)
                if vid != version['version_id'] or sentence.get('sentence_id',sid)!=sid or sentence.get('version_id',vid)!=vid:
                    raise ValueError('cross_version_evidence')
                result.append({'sentence_id':sid,'version_id':vid,'text':sentence['text'],'page_number':sentence.get('page_number')} | {
                    k:version[k] for k in ('url','content_date','last_modified','fetched_at')})
        return result
