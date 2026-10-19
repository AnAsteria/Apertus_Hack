"""EXTRA E3: queued refresh jobs are executed and recorded (fake crawl/build, no network)."""
from types import SimpleNamespace

from app.contracts import Job
from app.lifecycle.refresh_executor import find_source, run_queued
from app.repository import SqliteRepository


def src(sid, host):
    return SimpleNamespace(config=SimpleNamespace(source_id=sid, allowed_domains=[host]))


SOURCES = {'a.yaml': src('artorg', 'www.artorg.unibe.ch'), 'b.yaml': src('dcb', 'www.dcberne.com')}


def repo_with(tmp_path, *source_ids):
    repo = SqliteRepository(str(tmp_path / 'jobs.sqlite')); repo.init()
    for i, s in enumerate(source_ids):
        repo.put_job(Job(job_id=f'job_{i}', source_id=s, kind='refresh', state='queued', started_at=f'2026-10-18T00:0{i}:00Z'))
    return repo


def test_host_or_source_id_matches():
    assert find_source('www.artorg.unibe.ch', SOURCES, SOURCES.get).config.source_id == 'artorg'
    assert find_source('dcb', SOURCES, SOURCES.get).config.source_id == 'dcb'
    assert find_source('example.org', SOURCES, SOURCES.get) is None


def test_runs_one_job_records_counts_and_never_text(tmp_path):
    repo = repo_with(tmp_path, 'www.artorg.unibe.ch', 'dcb')
    crawled = []
    done = run_queued(repo, sources=SOURCES, load=SOURCES.get,
                      crawl_fn=lambda s: crawled.append(s.config.source_id) or {'counts': {'fetched': 3, 'new_versions': 1}, 'events': []},
                      build_fn=lambda: {'encoded_entries': 4, 'reused_windows': 100})
    assert crawled == ['artorg'] and len(done) == 1
    job = repo.get_job('job_0')
    assert job.state == 'succeeded' and job.counts == {'fetched': 3, 'new_versions': 1, 'encoded_entries': 4, 'reused_windows': 100}
    assert repo.get_job('job_1').state == 'queued'           # bounded: one job per run


def test_unknown_source_and_failures_are_codes_only(tmp_path):
    repo = repo_with(tmp_path, 'example.org', 'dcb')
    def boom(_):
        raise RuntimeError('page text that must not be stored')
    run_queued(repo, sources=SOURCES, load=SOURCES.get, crawl_fn=boom, build_fn=lambda: {}, max_jobs=2)
    assert repo.get_job('job_0').error_codes == ['unknown_source']
    failed = repo.get_job('job_1')
    assert failed.state == 'failed' and failed.error_codes == ['RuntimeError'] and failed.retry_count == 1


def test_unchanged_content_reports_no_new_encoding(tmp_path):
    repo = repo_with(tmp_path, 'dcb')
    run_queued(repo, sources=SOURCES, load=SOURCES.get, crawl_fn=lambda s: {'counts': {'unchanged_versions': 5}, 'events': []},
               build_fn=lambda: {'encoded_entries': 160, 'reused_windows': 22182, 'reused': True})
    assert repo.get_job('job_0').counts == {'unchanged_versions': 5, 'encoded_entries': 0, 'index_unchanged': 1}
