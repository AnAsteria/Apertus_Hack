"""Registry generation joins immutable input rows to reviewed audit decisions."""
import csv
import json
from pathlib import Path
from urllib.parse import urlsplit
import yaml
from app.contracts import SourceConfig
from .types import Source


def source_id(key: str) -> str:
    if key == 'artorg.unibe.ch':
        return 'artorg'
    if key == 'dcberne.com':
        return 'dcb'
    if key == 'www.unibe.ch':
        return 'unibe'
    return 'unibe-' + key.removesuffix('.unibe.ch').replace('.', '-')


def generate_registry(directory: Path) -> list[Path]:
    inventory = list(csv.DictReader((directory / 'unibe_inventory.csv').open(encoding='utf-8')))
    audit_rows = list(csv.DictReader((directory / 'unibe_inventory_audit.csv').open(encoding='utf-8')))
    audit = {r['inventory_key']: r for r in audit_rows}
    if len(audit) != len(audit_rows) or set(audit) != {r['Sous-domaine'] for r in inventory}:
        raise ValueError('inventory_audit_keys_mismatch')
    profiles = json.loads((directory / 'crawl_profiles.json').read_text())
    paths, exclusions = [], []
    out = directory / 'generated'
    out.mkdir(exist_ok=True)
    overrides = json.loads((directory / 'discovery_seeds.json').read_text())
    for row in inventory:
        key = row['Sous-domaine']
        a = audit[key]
        if a['input_url'] != row['URL']:
            raise ValueError('inventory_audit_url_mismatch')
        if a['decision'] != 'included':
            exclusions.append({'inventory_key': key, 'reason': a['decision_reason']})
            continue
        sid, tier = source_id(key), a['tier']
        seed = overrides.get(sid, {})
        starts = list(dict.fromkeys(seed.get('start_urls', [a['effective_url']]) + [a['effective_url']]))
        hosts = sorted({urlsplit(u).hostname for u in starts})
        # Exact verified hosts, not suffix or substring domain matching.
        config = SourceConfig(schema_version='1', source_id=sid, label=row['Description'],
                              start_urls=starts, allowed_domains=hosts, allowed_paths=['/'],
                              languages=['de', 'en', 'fr', 'it'],
                              max_pages=profiles['dev'][tier]['max_pages'],
                              max_depth=profiles['dev'][tier]['max_depth'],
                              requests_per_second=profiles['requests_per_second'],
                              focus_areas=['diabetes', 'oncology', 'neurology', 'medtech'],
                              refresh_default_hours=24)
        data = {'source': config.model_dump(), 'inventory_key': key, 'tier': tier,
                'labels': a['source_labels'].split(';'),
                'sitemaps': [u for u in a['declared_sitemaps'].split(';') if u],
                'profiles': {p: v[tier] for p, v in profiles.items() if p in ('dev', 'final')},
                'network': profiles['network']}
        path = out / (sid + '.yaml')
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding='utf-8')
        paths.append(path)
    (out / 'excluded.json').write_text(json.dumps(exclusions, ensure_ascii=False, indent=2) + '\n')
    (out / 'registry.json').write_text(json.dumps({'sources': [p.name for p in paths], 'excluded': exclusions}, ensure_ascii=False, indent=2) + '\n')
    return paths


def registry_paths(directory: Path) -> list[Path]:
    manifest = json.loads((directory / 'generated/registry.json').read_text())
    names = manifest['sources']
    if any(Path(name).name != name or not name.endswith('.yaml') for name in names):
        raise ValueError('invalid_registry_path')
    return [directory / 'generated' / name for name in names]


def load_source(path: Path, profile: str, max_pages: int | None = None) -> Source:
    raw = yaml.safe_load(path.read_text())
    limits = raw['profiles'][profile]
    values = {**raw['source'], **limits}
    if max_pages is not None:
        if max_pages < 1:
            raise ValueError('max_pages_must_be_positive')
        values['max_pages'] = max_pages
    config = SourceConfig(**values)
    if any(urlsplit(u).hostname not in config.allowed_domains for u in config.start_urls):
        raise ValueError('seed_outside_allowed_domains')
    network = raw.get('network', {})
    return Source(config=config, labels=raw['labels'], tier=raw['tier'], profile=profile,
                  sitemaps=raw.get('sitemaps', []),
                  max_sitemaps=network.get('max_sitemaps', 2),
                  max_bytes=network.get('max_response_bytes', 10_000_000),
                  max_discovered=network.get('max_discovered_urls', 1000))
