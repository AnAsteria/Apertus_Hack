"""Operator CLI. No source network traffic occurs when this module is imported."""
import argparse
import json
import os
from pathlib import Path
from app.ingest.config import generate_registry, load_source, registry_paths
from app.ingest.network import Fetcher
from app.ingest.pipeline import crawl
from app.storage.corpus import CorpusStore


def main():
    parser = argparse.ArgumentParser(description='Bounded public corpus ingestion (not query-time crawling)')
    parser.add_argument('command', choices=['generate', 'crawl', 'export'])
    parser.add_argument('--registry', type=Path, default=Path('config/sources'))
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('BERNMATCH_DATA_DIR', 'data')))
    parser.add_argument('--config', type=Path, action='append', help='Explicit source YAML; repeat for a bounded live source extension')
    parser.add_argument('--profile', choices=['dev', 'final'], default='dev')
    parser.add_argument('--source', action='append', default=[], help='Source id; repeat to select several')
    parser.add_argument('--max-pages', type=int, help='Explicit profile budget override, recorded in snapshot')
    parser.add_argument('--refresh', action='store_true', help='Explicitly re-fetch; does not retire absent URLs')
    args = parser.parse_args()
    if args.command == 'generate':
        paths = generate_registry(args.registry)
        print(json.dumps({'generated_sources': len(paths), 'directory': str(args.registry / 'generated')}))
        return
    store = CorpusStore(args.data_dir)
    if args.command == 'export':
        # JSONL on stdout; public data only. Store directly under DATA_DIR if saving.
        for record in store.active_records():
            print(json.dumps({k: [x.model_dump() if hasattr(x, 'model_dump') else x for x in v] if isinstance(v, list)
                              else v.model_dump() if hasattr(v, 'model_dump') else v
                              for k, v in record.items()}, ensure_ascii=False))
        return
    try:
        paths = args.config or registry_paths(args.registry)
    except FileNotFoundError:
        parser.error('No generated registry. Run generate first or supply --config.')
    if not paths:
        parser.error('No generated registry. Run generate first.')
    sources = [load_source(p, args.profile, args.max_pages) for p in paths]
    requested = set(args.source)
    if requested - {s.config.source_id for s in sources}:
        parser.error('Unknown source id')
    fetcher = Fetcher()
    try:
        for source in sources:
            if requested and source.config.source_id not in requested:
                continue
            def progress(sid, vid):
                # Small checkpoint after each page lets T07 consume an early snapshot.
                import sys
                print(json.dumps({'source_id': sid, 'stored_version_id': vid}), file=sys.stderr, flush=True)
            snapshot = crawl(source, store, fetcher, refresh=args.refresh, on_progress=progress)
            print(json.dumps(snapshot, ensure_ascii=False), flush=True)
    finally:
        fetcher.close()


if __name__ == '__main__':
    main()
