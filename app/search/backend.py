"""Stored-corpus hybrid fast path. Local CPU embeddings, never an LLM endpoint."""
import json
import os
import time
import uuid
from datetime import datetime,timezone
import numpy as np
from app.contracts import MAX_RESULTS, Result, SearchResponse
from app.storage.indexes import IndexStore
from .analysis import analyze,language_of,match_expression,query_terms,words
from .encoder import OnnxEncoder,digest
from .ranking import entity_max,reciprocal_rank_fusion,diversify,non_entity_page,DEMOTION
from .outcome import classify,thresholds
from .explain import channel_ranks,matched_words,reason as explain_reason
from . import rerank as rerank_mod
from .typehint import preferred_type,BOOST as TYPE_BOOST


def freshness(evidence, now=None):
    dates = []
    for item in evidence:
        raw = item['content_date'] or item['last_modified']
        if not raw:
            return 'unknown'
        try:
            date = datetime.fromisoformat(raw.replace('Z','+00:00'))
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            dates.append(date)
        except ValueError:
            return 'unknown'
    now = now or datetime.now(timezone.utc)
    return 'stale' if any((now-d).total_seconds()>365*86400 for d in dates) else 'fresh'


class HybridBackend:
    def __init__(self, directory, *, encoder=None, min_dense=None, abstain_dense=None, keyword_weight=None, mode=None, reranker=None):
        mode = mode or os.environ.get('BERNMATCH_SEARCH_MODE','hybrid')
        min_dense = float(os.environ.get('BERNMATCH_MIN_DENSE','.80')) if min_dense is None else min_dense
        # Query-level abstention: E5 similarities are compressed (~.80-.91), so a
        # per-candidate floor cannot reject an off-topic query. Chosen on development
        # queries and ad hoc off-topic probes only (see app/search/README.md).
        abstain_dense = float(os.environ.get('BERNMATCH_ABSTAIN_DENSE','.83')) if abstain_dense is None else abstain_dense
        if not 0 <= min_dense <= 1 or not 0 <= abstain_dense <= 1:
            raise ValueError('invalid_dense_threshold')
        self.abstain_dense = abstain_dense
        # Weight of the BM25 channel relative to dense in RRF (dense = 1). Chosen on the
        # development split only (see app/search/README.md).
        self.keyword_weight = float(os.environ.get('BERNMATCH_KEYWORD_WEIGHT','.25')) if keyword_weight is None else keyword_weight
        if self.keyword_weight < 0:
            raise ValueError('invalid_keyword_weight')
        if mode not in ('hybrid','dense','keyword'):
            raise ValueError('invalid_retrieval_mode')
        self.store = IndexStore(directory)
        self.manifest = json.loads((self.store.root/'manifest.json').read_text())
        for name,asset in self.manifest['assets'].items():
            if not name.startswith('model/') and digest(self.store.root/name) != asset['sha256']:
                raise ValueError('index_asset_hash_mismatch')
        self.entities,self.entries = self.store.metadata()
        self.vectors = np.load(self.store.root/'vectors.npy',mmap_mode='r',allow_pickle=False)
        self.vector_entries = np.load(self.store.root/'vector_entries.npy',mmap_mode='r',allow_pickle=False)
        if self.vectors.shape[0] != len(self.vector_entries) or self.vectors.ndim != 2:
            raise ValueError('index_shape_mismatch')
        self.encoder = encoder
        self.encoder_error = False
        if encoder is None and mode != 'keyword':
            try:
                self.encoder = OnnxEncoder(self.store.root/'model')
            except Exception:
                self.encoder_error = True
        self.min_dense,self.mode = min_dense,mode
        self.reranker = rerank_mod.load_from_env() if reranker is None else (reranker or None)

    def search(self, req):
        start = time.perf_counter()
        timing = {}
        limitations = ['Relevance signals identify potentially related source material; exact quotations alone do not validate semantic support.']
        if self.encoder_error:
            limitations.append('Local embedding model unavailable; keyword retrieval remains available.')
        if any(v['entity']['resolution_state']!='confirmed' for v in self.entities.values()):
            limitations.append('Some entity identities are provisional; unsupported fields remain empty.')
        enrichment = 'unavailable' if req.enrichment_requested else 'not_requested'
        # Edited needs/context enrich in their separate tasks. Do not silently
        # present an ignored constraint as enforced by the baseline fast path.
        if req.needs or req.company_context:
            limitations.append('Baseline retrieval uses the query text; needs/context interpretation is not integrated.')
        from app.lifecycle.serving import load_suppression
        from app.lifecycle.suppression import is_suppressed_entity
        policy = load_suppression()
        denied = {eid for eid,item in self.entities.items() if any(is_suppressed_entity(policy,
            entity_id=identifier,names=[item['entity']['name']],urls=item['entity']['canonical_profiles'])
            for identifier in [eid]+item['entity']['alias_entity_ids'])}
        allowed = {eid for eid,item in self.entities.items() if eid not in denied and item['entity']['status']!='retired'
                   and req.entity_type in (None,item['entity']['entity_type'])}
        if not req.query.strip() or not words(req.query) or not allowed:
            return self._response(req,[],limitations,enrichment,start,timing)
        query_language = language_of(req.query)
        t = time.perf_counter()
        keyword = entity_max(self.store.keyword(match_expression(query_terms(req.query))),self.entries,allowed) if self.mode!='dense' else {}
        timing['keyword'] = (time.perf_counter()-t)*1000
        t = time.perf_counter()
        dense = {}; vector_winners = {}; dense_ok = False
        if self.encoder is not None and self.mode!='keyword':
            try:
                query = self.encoder.encode([req.query],kind='query')[0]
                if query.shape != (self.vectors.shape[1],):
                    raise ValueError('query_dimension_mismatch')
                scores = self.vectors @ query
                for index in np.flatnonzero(scores>=self.min_dense):
                    entry_id = int(self.vector_entries[index])
                    old = vector_winners.get(entry_id)
                    if old is None or scores[index] > old[0]:
                        vector_winners[entry_id] = (float(scores[index]),int(index))
                dense = entity_max([(i,x[0]) for i,x in vector_winners.items()],self.entries,allowed)
                dense_ok = True
            except Exception:
                limitations.append('Local embedding computation failed; available keyword results are retained.')
        timing['dense'] = (time.perf_counter()-t)*1000
        best_dense = max((score for score,_ in dense.values()),default=0.)
        if dense_ok and best_dense < self.abstain_dense:
            limitations.append('No stored passage was similar enough to the request; support was not found in the indexed corpus.')
            return self._response(req,[],limitations,enrichment,start,timing,dense_ok=dense_ok,best_dense=best_dense,abstain=self.abstain_dense)
        t = time.perf_counter()
        fused = reciprocal_rank_fusion([keyword,dense],weights=[self.keyword_weight,1.])
        demoted = {eid for eid in fused if non_entity_page(self.entities[eid]['entity']['name'],
                   self.entities[eid]['entity']['canonical_profiles'])}
        for eid in demoted:
            fused[eid] *= DEMOTION
        type_hint = preferred_type(req.query) if req.entity_type is None and os.environ.get('BERNMATCH_TYPE_HINT','0')=='1' else None
        if type_hint:
            # EXTRA A3: soft preference only; nothing is filtered out.
            for eid in fused:
                if self.entities[eid]['entity']['entity_type']==type_hint:
                    fused[eid] *= TYPE_BOOST
        reranked = False
        if self.reranker is not None and fused:
            # EXTRA A1: cross-encoder over the best fused candidates; text = name + best passage.
            t_r = time.perf_counter()
            try:
                top = sorted(fused,key=lambda e:(-fused[e],e))[:rerank_mod.TOP_N]
                texts = {}
                for eid in top:
                    entry_id = (dense.get(eid) or keyword[eid])[1]
                    sids = self.entries[entry_id]['sentence_ids']
                    texts[eid] = self.entities[eid]['entity']['name']+'. '+' '.join(e['text'] for e in self.store.evidence(sids))
                fused = rerank_mod.rerank(fused,texts,req.query,self.reranker)
                for eid in demoted & set(fused):
                    fused[eid] *= DEMOTION
                reranked = True
            except Exception:
                limitations.append('Reranking failed; fused retrieval order is used.')
            timing['rerank'] = (time.perf_counter()-t_r)*1000
        representatives = {}
        # Use one representative vector per entity, independent of page count.
        for eid in fused:
            entry_id = (dense.get(eid) or keyword[eid])[1]
            if entry_id in vector_winners:
                vector_id = vector_winners[entry_id][1]
            else:
                vector_id = int(np.flatnonzero(self.vector_entries==entry_id)[0])
            representatives[eid] = self.vectors[vector_id]
        selected = diversify(fused,representatives,limit=MAX_RESULTS)
        timing['rank'] = (time.perf_counter()-t)*1000
        keyword_ranks,dense_ranks = channel_ranks(keyword),channel_ranks(dense)
        results = []
        for eid in selected:
            item = self.entities[eid]; entity = item['entity']
            # Prefer the strongest semantic passage when available; the lexical
            # ablation resolves its own best passage. Profiles cite stored text.
            entry_id = (dense.get(eid) or keyword[eid])[1]
            entry = self.entries[entry_id]
            sids = entry['sentence_ids']
            evidence = self.store.evidence(sids)
            # Include every sentence needed for surfaced claims. These references
            # were checked at build time, rather than accepting invented quotes.
            if item['claim_sentence_ids']:
                evidence += self.store.evidence(item['claim_sentence_ids'])
            evidence = list({e['sentence_id']:e for e in evidence}.values())
            if not evidence:
                continue
            evidence_language = entry.get('language')
            matched = matched_words(req.query,[e['text'] for e in evidence],evidence_language) if eid in keyword else []
            reason = explain_reason(keyword_rank=keyword_ranks.get(eid),dense_rank=dense_ranks.get(eid),matched=matched,
                                    query_language=query_language,evidence_language=evidence_language,
                                    demoted=eid in demoted,former=entity['status']=='former')
            results.append(Result(entity_id=eid,entity_type=entity['entity_type'],rank=len(results)+1,
                display_name=entity['name'],fields=item['fields'],reason=reason,evidence=evidence,
                freshness=freshness(evidence),retrieval={'bm25':keyword.get(eid,(None,None))[0],
                'dense':dense.get(eid,(None,None))[0],'rrf':fused[eid],'aggregation':'max_before_rrf',
                'entry_kind':entry['kind'],'demoted_listing_page':eid in demoted,'query_language':query_language,'mode':self.mode,
                'keyword_rank':keyword_ranks.get(eid),'dense_rank':dense_ranks.get(eid),'matched_terms':matched,
                'evidence_language':evidence_language,'channels':[c for c,ranks in (('keyword',keyword_ranks),('dense',dense_ranks)) if eid in ranks],
                'query_variant':'original','reranked':reranked,'type_hint':type_hint,
                'resolution_state':entity['resolution_state'],'entity_status':entity['status'],
                'model':self.manifest['model']['repo'],'generation':self.manifest['generation']}))
        return self._response(req,results,limitations,enrichment,start,timing,dense_ok=dense_ok,best_dense=best_dense,abstain=self.abstain_dense)

    @staticmethod
    def _response(req,results,limitations,enrichment,start,timing,*,dense_ok=False,best_dense=0.,abstain=0.):
        if not results:
            limitations.append('Support was not found above the retrieval thresholds in the indexed corpus.')
        outcome,suggestions,note = classify(req.query,results,dense_ok=dense_ok,best_dense=best_dense,abstain_dense=abstain)
        if outcome=='too_broad':
            # Examples only: a broad request has no defensible ranking of ten matches.
            results = [r.model_copy(update={'rank':i}) for i,r in enumerate(results[:5],1)]
        if note:
            limitations.append(note)
        timing['total'] = (time.perf_counter()-start)*1000
        return SearchResponse(schema_version='1',request_id='req_'+uuid.uuid4().hex,revision=req.revision,
                              results=results,limitations=limitations,enrichment_state=enrichment,timing_ms=timing,
                              outcome=outcome,suggestions=suggestions)
