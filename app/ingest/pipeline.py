"""One-shot, bounded ingestion over persistent snapshots; no query integration."""
import time
import uuid
import xml.etree.ElementTree as ET
from collections import Counter, deque
from datetime import datetime, timezone
from app.ingest.extract import PARSER_VERSION, parse
from app.ingest.network import canonical_url, in_scope
from app.ingest.types import IngestError, Parsed, Section

FOCUS_TERMS = {
    'diabetes': ('diabet', 'insulin', 'glucose', 'glukose'),
    'oncology': ('oncol', 'onkolog', 'cancer', 'krebs', 'tumor', 'tumour'),
    'neurology': ('neuro', 'brain', 'hirn', 'cerebr'),
    'medtech': ('medtech', 'biomedical engineering', 'biomedizin', 'medical device', 'robot'),
}
ROUTED = {'person', 'unit', 'project', 'infrastructure', 'service'}


def restore_parsed(data):
    return Parsed(**{**data, 'sections': [Section(**s) for s in data['sections']]})


def crawl(source, store, fetcher, refresh=False, on_progress=None):
    start = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    queue = deque((u, 0) for u in dict.fromkeys(source.config.start_urls + store.source_urls(source.config.source_id)))
    seen, known = set(), set(source.config.start_urls)
    counts, language_counts, type_counts, focus_counts = Counter(), Counter(), Counter(), Counter()
    events, extraction_queue, document_versions = [], [], []
    initial_requests, initial_retries = fetcher.requests, fetcher.retries
    # Sitemap discovery is lazy: a fully reused cached source needs no network calls.
    maps_loaded = False
    maps = list(source.sitemaps)
    while queue and counts['page_slots'] < source.config.max_pages:
        raw_url, depth = queue.popleft()
        try:
            url = canonical_url(raw_url)
        except IngestError:
            counts['excluded'] += 1
            continue
        if url in seen:
            continue
        seen.add(url)
        counts['discovered'] += 1
        if not in_scope(url, source):
            events.append({'url': url, 'reason': 'outside_scope'})
            counts['excluded'] += 1
            continue
        counts['page_slots'] += 1
        page = None
        try:
            cached = None if refresh else store.cached_page(url)
            if cached is not None:
                parsed = restore_parsed(cached)
                counts['reused'] += 1
            else:
                page = fetcher.fetch(raw_url, source)
                # A redirect alias already fetched in this run can be reused without
                # creating duplicate version records, while preserving the fetch record.
                counts['fetched'] += 1
                parsed = parse(page)
                parsed.links = [u for u in parsed.links if in_scope(u, source)]
                parsed.variants = [canonical_url(u) for u in parsed.variants if in_scope(u, source)]
                version, unchanged = store.ingest(source.config.source_id, source.labels,
                                                  page, parsed, PARSER_VERSION)
                counts['unchanged_versions' if unchanged else 'new_versions'] += 1
                document_versions.append(version.version_id)
                counts['parsed'] += 1
                if parsed.page_type in ROUTED:
                    extraction_queue.append(version.version_id)
                if on_progress:
                    on_progress(source.config.source_id, version.version_id)
            language_counts[parsed.language or 'unknown'] += 1
            type_counts[parsed.page_type] += 1
            tagged = False
            for tag, terms in FOCUS_TERMS.items():
                if any(term in parsed.text.lower() for term in terms):
                    focus_counts[tag] += 1
                    tagged = True
            if not tagged:
                counts['outside_focus_pages'] += 1
            if depth < source.config.max_depth:
                # Research/type-specific links before generic navigation; stable order.
                links = sorted(parsed.links, key=lambda u: not any(k in u.lower() for k in (
                    'research', 'forschung', 'project', 'people', 'personen', 'facilit', 'service')))
                for candidate in links:
                    if candidate not in known and len(known) < source.max_discovered:
                        queue.append((candidate, depth + 1))
                        known.add(candidate)
            if not cached and not maps_loaded:
                maps_loaded = True
                for policy in fetcher.robots.values():
                    if policy is not None:
                        maps += list(policy.sitemaps or [])
                map_queue = deque(dict.fromkeys(maps))
                map_seen = set()
                while map_queue and len(map_seen) < source.max_sitemaps:
                    sitemap_url = map_queue.popleft()
                    if sitemap_url in map_seen or not in_scope(sitemap_url, source):
                        continue
                    map_seen.add(sitemap_url)
                    try:
                        result = fetcher.fetch(sitemap_url, source)
                        if result.body.startswith(b'\x1f\x8b'):
                            raise IngestError('compressed_sitemap_unsupported')
                        tree = ET.fromstring(result.body)
                        if tree.tag.rsplit('}', 1)[-1] not in ('urlset', 'sitemapindex'):
                            raise IngestError('invalid_sitemap')
                        for loc in tree.iter():
                            if loc.tag.rsplit('}', 1)[-1] != 'loc' or not loc.text:
                                continue
                            candidate = loc.text.strip()
                            if not in_scope(candidate, source):
                                continue
                            if tree.tag.endswith('sitemapindex'):
                                map_queue.append(candidate)
                            elif candidate not in known and len(known) < source.max_discovered:
                                queue.append((candidate, 1))
                                known.add(candidate)
                    except (IngestError, ET.ParseError) as error:
                        counts['sitemap_failures'] += 1
                        events.append({'url': sitemap_url, 'reason': getattr(error, 'code', 'invalid_sitemap')})
        except IngestError as error:
            if page is not None:
                store.record_fetch(page, reason=error.code)
            unsupported = error.code in ('scanned_or_empty_pdf', 'encrypted_pdf', 'invalid_pdf',
                                        'unsupported_media_type', 'js_rendered_candidate', 'no_usable_text')
            counts['unsupported' if unsupported else 'failed'] += 1
            events.append({'url': url, 'reason': error.code})
    store.link_variants()
    counts['network_requests'] = fetcher.requests - initial_requests
    counts['retries'] = fetcher.retries - initial_retries
    counts['remaining_discovered'] = len(queue)
    snapshot = {
        'schema_version': '1', 'snapshot_id': 'snapshot_' + uuid.uuid4().hex,
        'source_id': source.config.source_id, 'labels': source.labels, 'tier': source.tier,
        'profile': source.profile, 'started_at': started_at,
        'completed_at': datetime.now(timezone.utc).isoformat(), 'source_config': source.config.model_dump(),
        'network_limits': {'max_sitemaps': source.max_sitemaps, 'max_bytes': source.max_bytes,
                           'max_discovered': source.max_discovered},
        'refresh': refresh, 'duration_seconds': round(time.monotonic() - start, 6),
        'counts': dict(counts), 'languages': dict(language_counts), 'page_types': dict(type_counts),
        'focus_keyword_counts': dict(focus_counts), 'events': events,
        'newly_fetched_version_ids': list(dict.fromkeys(document_versions)),
        'extraction_queue': list(dict.fromkeys(extraction_queue)),
        'limitations': ['Focus tags are keyword routing signals, not semantic expertise claims.',
                        'Only a bounded snapshot; unsupported/failed pages remain visible.',
                        'No search index or LLM extraction is built by this job.'],
    }
    store.save_snapshot(snapshot)
    return snapshot
