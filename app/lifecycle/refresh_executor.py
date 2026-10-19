"""EXTRA E3: execute queued manual refresh jobs (T12/T13). Operator command, never run by a query.

    python -m app.lifecycle.refresh_executor --jobs-db <data>/bernmatch.sqlite --corpus-dir <corpus> \
        --serve-dir <serving dir> --model-dir <serving dir>/indexes/<gen>/model [--knowledge-dir <dir>] \
        [--extra-config config/sources/examples/x.yaml] [--profile final] [--max-jobs 1]

One queued `refresh` job is taken at a time: the matching source is re-fetched (`refresh=True`:
cached pages are not reused; changed content becomes a new immutable version, unchanged content
keeps its version), then an incremental index generation is built that reuses every vector whose
text did not change, and READY is swapped atomically. Absent pages are NOT retired here: removal
needs separate confirmation (suppression list, docs/data-policy.md). Errors are recorded as codes
on the job, never as source or request text.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.contracts import Job
from app.repository import SqliteRepository


def _now():
    return datetime.now(timezone.utc).isoformat()


def find_source(job_source: str, paths, load):
    """Match the admin's source id (a source id or a host such as www.artorg.unibe.ch)."""
    for p in paths:
        src = load(p)
        cfg = src.config
        hosts = {h.casefold().removeprefix('www.') for h in cfg.allowed_domains}
        if job_source == cfg.source_id or job_source.casefold().removeprefix('www.') in hosts:
            return src
    return None


def run_queued(repo, *, sources, load, crawl_fn, build_fn, max_jobs=1):
    """Run up to `max_jobs` queued refresh jobs. `crawl_fn(source) -> snapshot dict`,
    `build_fn() -> build manifest dict`. Returns the updated jobs."""
    done = []
    queued = sorted((j for j in repo.list_jobs() if j.kind == 'refresh' and j.state == 'queued'),
                    key=lambda j: j.started_at or '')
    for job in queued[:max_jobs]:
        source = find_source(job.source_id, sources, load)
        if source is None:
            job = job.model_copy(update={'state': 'failed', 'ended_at': _now(), 'error_codes': ['unknown_source']})
            repo.put_job(job); done.append(job); continue
        job = job.model_copy(update={'state': 'running', 'started_at': job.started_at or _now()})
        repo.put_job(job)
        try:
            snap = crawl_fn(source)
            counts = {k: int(v) for k, v in (snap.get('counts') or {}).items() if isinstance(v, int)}
            manifest = build_fn()
            if manifest.get('reused'):
                # Identical content: the current generation is kept as is (no new build).
                counts.update(encoded_entries=0, index_unchanged=1)
            else:
                counts.update(encoded_entries=int(manifest.get('encoded_entries') or 0),
                              reused_windows=int(manifest.get('reused_windows') or 0))
            state = 'succeeded' if not snap.get('events') else 'partial'
            job = job.model_copy(update={'state': state, 'ended_at': _now(), 'counts': counts})
        except Exception as exc:  # code only: messages can contain source text
            job = job.model_copy(update={'state': 'failed', 'ended_at': _now(),
                                         'error_codes': [type(exc).__name__], 'retry_count': job.retry_count + 1})
        repo.put_job(job); done.append(job)
    return done


def main(argv=None) -> int:
    from app.ingest.config import load_source, registry_paths
    from app.ingest.network import Fetcher
    from app.ingest.pipeline import crawl
    from app.storage.corpus import CorpusStore
    from app.search.build import build_index
    from app.search.encoder import OnnxEncoder
    ap = argparse.ArgumentParser(prog='python -m app.lifecycle.refresh_executor')
    ap.add_argument('--jobs-db', required=True); ap.add_argument('--corpus-dir', type=Path, required=True)
    ap.add_argument('--serve-dir', type=Path, required=True); ap.add_argument('--model-dir', type=Path, required=True)
    ap.add_argument('--knowledge-dir', type=Path); ap.add_argument('--registry', type=Path, default=Path('config/sources'))
    ap.add_argument('--extra-config', type=Path, action='append', default=[])
    ap.add_argument('--profile', choices=['dev', 'final'], default='final'); ap.add_argument('--max-jobs', type=int, default=1)
    a = ap.parse_args(argv)
    try:
        paths = registry_paths(a.registry)
    except FileNotFoundError:
        paths = []
    paths = list(paths) + list(a.extra_config)
    store = CorpusStore(a.corpus_dir)

    def crawl_fn(source):
        fetcher = Fetcher()
        try:
            return crawl(source, store, fetcher, refresh=True)
        finally:
            fetcher.close()

    def build_fn():
        extra, claims = (), ()
        if a.knowledge_dir:
            extra = [json.loads(l) for l in (a.knowledge_dir / 'entities.jsonl').open(encoding='utf-8')]
            claims = [json.loads(l) for l in (a.knowledge_dir / 'claims.jsonl').open(encoding='utf-8')]
        return build_index(list(store.active_records()), a.serve_dir, OnnxEncoder(a.model_dir),
                           extra_entities=extra, claims=claims)

    repo = SqliteRepository(a.jobs_db); repo.init()
    jobs = run_queued(repo, sources=paths, load=lambda p: load_source(p, a.profile), crawl_fn=crawl_fn, build_fn=build_fn,
                      max_jobs=a.max_jobs)
    print(json.dumps([j.model_dump() for j in jobs], indent=1))
    return 0 if all(j.state != 'failed' for j in jobs) else 1


if __name__ == '__main__':
    sys.exit(main())
