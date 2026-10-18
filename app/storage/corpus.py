"""Persistent public corpus. Reads perform no network or model calls.

Separate from operational/feedback storage. Original evidence versions are immutable.
"""
import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import asdict
from pathlib import Path
from app.contracts import (Document, Version, Sentence, Passage, Entity, content_hash,
                           make_document_id, make_version_id, make_passage_id, make_sentence_id)


class CorpusStore:
    def __init__(self, data_dir):
        self.root = Path(data_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'corpus.sqlite'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, url TEXT UNIQUE, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS versions (id TEXT PRIMARY KEY, document_id TEXT, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sentences (id TEXT PRIMARY KEY, version_id TEXT, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS active_versions (document_id TEXT PRIMARY KEY, version_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS entities (id TEXT PRIMARY KEY, document_id TEXT, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS passage_entities (passage_id TEXT, entity_id TEXT,
                    PRIMARY KEY (passage_id,entity_id));
                CREATE TABLE IF NOT EXISTS pages (url TEXT PRIMARY KEY, document_id TEXT, parsed TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS variants (document_id TEXT, url TEXT, PRIMARY KEY(document_id,url));
                CREATE TABLE IF NOT EXISTS labels (document_id TEXT, label TEXT, PRIMARY KEY(document_id,label));
                CREATE TABLE IF NOT EXISTS snapshots (id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS sentence_version ON sentences(version_id);
            ''')

    def connect(self):
        return sqlite3.connect(self.path)

    def source_urls(self, source_id):
        with self.connect() as db:
            rows = db.execute('SELECT p.url,d.body FROM pages p JOIN documents d ON p.document_id=d.id').fetchall()
        return [url for url, body in rows if json.loads(body)['source_id'] == source_id]

    def cached_page(self, url):
        with self.connect() as db:
            row = db.execute('SELECT parsed FROM pages WHERE url=?', (url,)).fetchone()
        return json.loads(row[0]) if row else None

    def ingest(self, source_id, labels, page, parsed, parser_version):
        from app.ingest.network import canonical_url
        canonical = canonical_url(page.url)
        # Reuse a document identity after an audited redirect, irrespective of labels.
        with self.connect() as db:
            previous = db.execute('SELECT body FROM documents WHERE url=?', (canonical,)).fetchone()
            doc = Document.model_validate_json(previous[0]) if previous else Document(
                schema_version='1', document_id=make_document_id(source_id, canonical),
                source_id=source_id, canonical_url=canonical)
            version_id = make_version_id(doc.document_id, content_hash(parsed.text), parser_version)
            existing = db.execute('SELECT body FROM versions WHERE id=?', (version_id,)).fetchone()
            if existing:
                version = Version.model_validate_json(existing[0])
            else:
                passages, sentences, section_passages = [], [], []
                n = 0
                # Import locally: consumers can read storage without installing parsers.
                from app.ingest.extract import split_sentences
                for section in parsed.sections:
                    chunks, chunk = [], []
                    for sentence in split_sentences(section.text):
                        if chunk and sum(map(len, chunk)) + len(sentence) > 1600:
                            chunks.append(chunk)
                            chunk = []
                        chunk.append(sentence)
                    if chunk:
                        chunks.append(chunk)
                    for group in chunks:
                        pid = make_passage_id(version_id, len(passages) + 1)
                        ids = []
                        for text in group:
                            n += 1
                            sid = make_sentence_id(version_id, n)
                            ids.append(sid)
                            sentences.append(Sentence(schema_version='1', sentence_id=sid,
                                version_id=version_id, passage_id=pid, text=text,
                                page_number=section.page_number))
                        passages.append(Passage(passage_id=pid, sentence_ids=ids,
                                                page_number=section.page_number))
                        section_passages.append((section.heading, pid))
                version = Version(schema_version='1', version_id=version_id, document_id=doc.document_id,
                    url=page.url, redirects=page.redirects, fetched_at=page.fetched_at,
                    content_date=parsed.content_date, last_modified=page.last_modified or parsed.last_modified,
                    content_hash=content_hash(parsed.text), parser_version=parser_version,
                    language=parsed.language, media_type=page.media_type, page_type=parsed.page_type,
                    state='active', passages=passages)
                db.execute('INSERT INTO versions VALUES (?,?,?)',
                           (version_id, doc.document_id, version.model_dump_json()))
                for sentence in sentences:
                    db.execute('INSERT INTO sentences VALUES (?,?,?)',
                               (sentence.sentence_id, version_id, sentence.model_dump_json()))
                # Stubs are retrieval anchors, never confirmed people/facts or contacts.
                etype = parsed.page_type if parsed.page_type in ('person','unit','project','infrastructure','service') else 'unit'
                for heading, pid in section_passages:
                    # Directory publication/news headings are not automatically units.
                    # Only explicit programme headings get separate provisional anchors.
                    section_unit = parsed.page_type == 'directory' and re.search(r' - [A-Z]{2,6}$', heading)
                    name = heading if section_unit else parsed.title
                    eid = 'ent_' + uuid.uuid5(uuid.NAMESPACE_URL,
                                              doc.document_id + '\n' + etype + '\n' + name).hex
                    entity = Entity(schema_version='1', entity_id=eid, entity_type=etype, name=name,
                        canonical_profiles=[canonical], status='unknown', resolution_state='uncertain')
                    db.execute('INSERT OR IGNORE INTO entities VALUES (?,?,?)',
                               (eid, doc.document_id, entity.model_dump_json()))
                    db.execute('INSERT OR IGNORE INTO passage_entities VALUES (?,?)', (pid, eid))
            db.execute('INSERT OR REPLACE INTO documents VALUES (?,?,?)',
                       (doc.document_id, canonical, doc.model_dump_json()))
            db.execute('INSERT OR REPLACE INTO active_versions VALUES (?,?)', (doc.document_id, version_id))
            for label in labels:
                db.execute('INSERT OR IGNORE INTO labels VALUES (?,?)', (doc.document_id, label))
            for variant in parsed.variants:
                db.execute('INSERT OR IGNORE INTO variants VALUES (?,?)', (doc.document_id, variant))
            cached = json.dumps(asdict(parsed), ensure_ascii=False)
            for url in {canonical_url(page.requested_url), canonical}:
                db.execute('INSERT OR REPLACE INTO pages VALUES (?,?,?)', (url, doc.document_id, cached))
        self.record_fetch(page, version_id)
        return version, bool(existing)

    def record_fetch(self, page, version_id=None, reason=None):
        """Retain provenance even when content is unsupported and has no evidence version."""
        raw_hash = hashlib.sha256(page.body).hexdigest()
        raw = self.root / 'raw' / raw_hash
        raw.parent.mkdir(exist_ok=True)
        if not raw.exists():
            raw.write_bytes(page.body)
        meta = self.root / 'fetches'
        meta.mkdir(exist_ok=True)
        fetch_id = uuid.uuid4().hex
        (meta / (fetch_id + '.json')).write_text(json.dumps({
            'requested_url': page.requested_url, 'url': page.url, 'redirects': page.redirects,
            'fetched_at': page.fetched_at, 'last_modified': page.last_modified,
            'raw_sha256': raw_hash, 'version_id': version_id, 'reason': reason}, ensure_ascii=False))

    def link_variants(self):
        with self.connect() as db:
            pairs = db.execute('SELECT v.document_id,d.id FROM variants v JOIN documents d ON v.url=d.url').fetchall()
            # Link identical-text candidates while retaining separate records.
            by_hash = {}
            for doc_id, body in db.execute('SELECT v.document_id,v.body FROM versions v JOIN active_versions a ON a.version_id=v.id').fetchall():
                digest = json.loads(body)['content_hash']
                for other in by_hash.get(digest, []):
                    if other != doc_id:
                        pairs.append((doc_id, other))
                by_hash.setdefault(digest, []).append(doc_id)
            for first, second in pairs:
                if first == second:
                    continue
                for current, other in ((first, second), (second, first)):
                    row = db.execute('SELECT body FROM documents WHERE id=?', (current,)).fetchone()
                    doc = Document.model_validate_json(row[0])
                    if other not in doc.language_variant_document_ids:
                        doc.language_variant_document_ids.append(other)
                        db.execute('UPDATE documents SET body=? WHERE id=?', (doc.model_dump_json(), current))

    def get_sentence(self, version_id, sentence_id):
        with self.connect() as db:
            row = db.execute('SELECT body FROM sentences WHERE id=? AND version_id=?',
                             (sentence_id, version_id)).fetchone()
        if row is None:
            raise KeyError('evidence_unavailable')
        return Sentence.model_validate_json(row[0])

    def active_records(self):
        """Public T07/T09 handoff. Only active versions, with exact sentence records."""
        with self.connect() as db:
            rows = db.execute('SELECT d.body,v.body FROM active_versions a '
                              'JOIN documents d ON d.id=a.document_id JOIN versions v ON v.id=a.version_id').fetchall()
            result = []
            for document, version_body in rows:
                version = Version.model_validate_json(version_body)
                sentences = [Sentence.model_validate_json(r[0]) for r in db.execute(
                    'SELECT body FROM sentences WHERE version_id=?', (version.version_id,)).fetchall()]
                entities = [Entity.model_validate_json(r[0]) for r in db.execute(
                    'SELECT DISTINCT e.body FROM entities e JOIN passage_entities pe ON pe.entity_id=e.id '
                    'WHERE pe.passage_id LIKE ?', (version.version_id + ':p%',)).fetchall()]
                mappings = dict()
                for pid, eid in db.execute('SELECT passage_id,entity_id FROM passage_entities WHERE passage_id LIKE ?',
                                          (version.version_id + ':p%',)).fetchall():
                    mappings.setdefault(pid, []).append(eid)
                labels = [r[0] for r in db.execute('SELECT label FROM labels WHERE document_id=? ORDER BY label', (version.document_id,)).fetchall()]
                result.append({'document': Document.model_validate_json(document), 'version': version, 'source_labels': labels,
                               'sentences': sorted(sentences, key=lambda s: int(s.sentence_id.rsplit(':s', 1)[1])),
                               'entities': entities, 'passage_entity_ids': mappings})
        return result

    def save_snapshot(self, snapshot):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO snapshots VALUES (?,?)',
                       (snapshot['snapshot_id'], json.dumps(snapshot, ensure_ascii=False)))
        out = self.root / 'snapshots'
        out.mkdir(exist_ok=True)
        (out / (snapshot['snapshot_id'] + '.json')).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
