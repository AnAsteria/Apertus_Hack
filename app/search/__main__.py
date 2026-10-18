"""Operator commands. Explicit build requires already-downloaded model assets."""
import argparse
import json
import os
import sys
from pathlib import Path


def read_export(path):
    from app.contracts import Document,Version,Sentence,Entity
    records=[]
    with Path(path).open() as stream:
        for line in stream:
            row=json.loads(line)
            records.append({'document':Document.model_validate(row['document']),
                'version':Version.model_validate(row['version']),
                'sentences':[Sentence.model_validate(s) for s in row['sentences']],
                'entities':[Entity.model_validate(e) for e in row['entities']],
                'source_labels':row['source_labels'],'passage_entity_ids':row['passage_entity_ids']})
    return records


def main():
    p=argparse.ArgumentParser(description='Build/query a local stored-corpus index; never crawl')
    p.add_argument('command',choices=['fetch-model','build','query','inspect','package'])
    p.add_argument('--data-dir',type=Path,default=Path(os.environ.get('BERNMATCH_DATA_DIR','data')))
    p.add_argument('--corpus-dir',type=Path)
    p.add_argument('--corpus-jsonl',type=Path,help='T06 JSONL export, alternative to a corpus directory')
    p.add_argument('--model-dir',type=Path)
    p.add_argument('--knowledge-dir',type=Path,help='T08 knowledge directory with entities.jsonl and claims.jsonl')
    p.add_argument('--knowledge-file',type=Path,help='Optional explicit T08 Entity/Claim arrays; unavailable payloads are not invented')
    p.add_argument('--model',choices=['small','base'],default='small')
    p.add_argument('--output',type=Path)
    p.add_argument('--query')
    p.add_argument('--entity-type',choices=['person','unit','project','infrastructure','service'])
    p.add_argument('--mode',choices=['hybrid','dense','keyword'],default='hybrid')
    args=p.parse_args()
    if args.command=='fetch-model':
        if not args.model_dir:
            p.error('fetch-model requires --model-dir')
        from .models import fetch_model
        print(json.dumps(fetch_model(args.model,args.model_dir),indent=2))
    elif args.command=='build':
        if bool(args.corpus_dir)==bool(args.corpus_jsonl) or not args.model_dir:
            p.error('build requires exactly one of --corpus-dir / --corpus-jsonl, plus --model-dir')
        if args.corpus_dir and not (args.corpus_dir/'corpus.sqlite').is_file():
            p.error('stored corpus is unavailable; ingestion is an explicit separate operation')
        from app.storage.corpus import CorpusStore
        from .encoder import OnnxEncoder
        from .build import build_index
        if args.knowledge_file and args.knowledge_dir:
            p.error('choose --knowledge-dir or --knowledge-file, not both')
        payload=json.loads(args.knowledge_file.read_text()) if args.knowledge_file else {}
        if args.knowledge_dir:
            payload={name:[json.loads(line) for line in (args.knowledge_dir/(name+'.jsonl')).open()]
                     for name in ('entities','claims')}
        encoder=OnnxEncoder(args.model_dir)
        def progress(done,total):
            print(json.dumps({'embedded_entries':done,'total_entries':total}),file=sys.stderr,flush=True)
        records = read_export(args.corpus_jsonl) if args.corpus_jsonl else CorpusStore(args.corpus_dir).active_records()
        manifest=build_index(records,args.data_dir,encoder,
                             extra_entities=payload.get('entities',[]),claims=payload.get('claims',[]),progress=progress)
        print(json.dumps(manifest,indent=2))
    elif args.command=='package':
        if not args.output:
            p.error('package requires --output')
        from .bundle import package_bundle
        print(json.dumps(package_bundle(args.data_dir,args.output),indent=2))
    else:
        from app.storage.indexes import current_generation
        current=current_generation(args.data_dir)
        if not current:
            p.error('no valid READY search generation')
        directory,manifest=current
        if args.command=='inspect':
            print(json.dumps(manifest,indent=2))
        else:
            if not args.query:
                p.error('query requires --query')
            from .backend import HybridBackend
            from app.contracts import SearchRequest
            result=HybridBackend(directory,mode=args.mode).search(SearchRequest(schema_version='1',query=args.query,
                                                        revision=1,entity_type=args.entity_type))
            print(result.model_dump_json(indent=2))


if __name__=='__main__':
    main()
