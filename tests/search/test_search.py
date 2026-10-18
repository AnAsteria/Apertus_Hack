"""Deterministic synthetic risk checks. No downloaded weights, HTTP or inference."""
import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.contracts import (Document,Version,Sentence,Passage,Entity,Claim,EvidencePair,SearchRequest,
                           content_hash,make_document_id,make_version_id,make_passage_id,make_sentence_id)
from app.search.build import build_index
from app.search.backend import HybridBackend,freshness
from app.search.encoder import normalize
from app.search.ranking import entity_max,reciprocal_rank_fusion,diversify
from app.search.analysis import analyze,query_terms,match_expression
from app.storage.indexes import current_generation


class FixtureEncoder:
    """Synthetic concept vectors test plumbing only, never real-model quality."""
    dimensions=8
    def __init__(self,root):
        self.root=Path(root); self.root.mkdir(exist_ok=True)
        (self.root/'fixture.txt').write_text('SYNTHETIC encoder assets, not a real model')
        self.manifest={'repo':'synthetic/test-only','revision':'0'*40,'license':'synthetic','files':{}}
        self.calls=0
    def encode(self,texts,kind='query'):
        self.calls+=1
        vectors=[]
        for text in texts:
            text=text.casefold(); v=np.zeros(8,dtype=np.float32)
            for i,keys in enumerate([('laser','instrument'),('glucose','insulin','diabet'),('neuro','brain'),('absent','zxq'),('project',),('service',),('sequenc',)]):
                if any(k in text for k in keys): v[i]=1
            v[7]=.01
            vectors.append(v)
        return normalize(vectors) if vectors else np.empty((0,8),dtype=np.float32)
    def encode_windows(self,texts,kind='passage',progress=None):
        return self.encode(texts,kind),np.arange(len(texts),dtype=np.int32)


def record(key='a',text='Laser precision instruments for biomedical research.',etype='unit',eid=None):
    url='https://fixture.invalid/'+key
    did=make_document_id('fixture',url); vid=make_version_id(did,content_hash(text),'test-v1')
    pid=make_passage_id(vid,1); sid=make_sentence_id(vid,1)
    entity=Entity(schema_version='1',entity_id=eid or 'ent_'+key,entity_type=etype,name=key+' '+etype,
                  canonical_profiles=[url],status='unknown',resolution_state='uncertain')
    sentence=Sentence(schema_version='1',sentence_id=sid,version_id=vid,passage_id=pid,text=text)
    version=Version(schema_version='1',version_id=vid,document_id=did,url=url,fetched_at='2026-10-18T12:00:00Z',
                    content_hash=content_hash(text),parser_version='test-v1',media_type='text/html',page_type=etype,
                    state='active',language='en',passages=[Passage(passage_id=pid,sentence_ids=[sid])])
    return {'document':Document(schema_version='1',document_id=did,source_id='fixture',canonical_url=url),
            'version':version,'sentences':[sentence],'entities':[entity],'source_labels':['fixture'],
            'passage_entity_ids':{pid:[entity.entity_id]}}


@pytest.fixture
def built(tmp_path):
    encoder=FixtureEncoder(tmp_path/'model')
    records=[record(),record('b','Glucose and insulin diabetes research.',etype='project')]
    data=tmp_path/'data'
    manifest=build_index(records,data,encoder)
    directory,_=current_generation(data)
    return data,directory,encoder,records,manifest


def req(text='laser',**kwargs):
    return SearchRequest(schema_version='1',query=text,revision=7,**kwargs)


def test_duplicate_pages_cannot_add_entity_rank_votes():
    entries=[{'entity_ids':['ent_a']},{'entity_ids':['ent_b']}]+[{'entity_ids':['ent_a']}]*100
    scores=[(0,.9),(1,.8)]+[(i,.9) for i in range(2,102)]
    channel=entity_max(scores,entries,{'ent_a','ent_b'})
    fused=reciprocal_rank_fusion([channel,channel])
    assert fused=={'ent_a':2/61,'ent_b':2/62}
    assert channel['ent_a'][1]==0


def test_mmr_keeps_high_relevance_without_institutional_quotas():
    scores={'a':1.,'duplicate':.99,'different':.98,'weak':.2}
    vectors={'a':np.array([1.,0.]),'duplicate':np.array([1.,0.]),'different':np.array([0.,1.]),'weak':np.array([0.,1.])}
    assert diversify(scores,vectors,limit=3)==['a','different','duplicate']


def test_stemming_compounds_and_multilingual_terms():
    assert set(analyze('Krebserkrankungen','de')) & set(query_terms('Krebs'))
    assert analyze('cancers','en')==analyze('cancer','en')
    assert analyze('inflammations','fr')==analyze('inflammation','fr')
    assert analyze('strumenti','it')==analyze('strumento','it')
    assert not match_expression(query_terms('" OR * ; DROP TABLE x --')).startswith('" OR')


def test_exact_evidence_and_no_llm_network(built,monkeypatch):
    data,directory,encoder,records,_=built
    backend=HybridBackend(directory,encoder=encoder)
    monkeypatch.setattr(socket.socket,'connect',lambda *args: (_ for _ in ()).throw(AssertionError('network forbidden')))
    response=backend.search(req(enrichment_requested=True))
    assert response.revision==7 and response.enrichment_state=='unavailable'
    assert response.results[0].entity_id=='ent_a'
    evidence=response.results[0].evidence[0]
    assert evidence.text==records[0]['sentences'][0].text
    assert evidence.version_id==records[0]['version'].version_id
    assert response.results[0].fields=={}
    assert response.timing_ms['total']>=response.timing_ms['dense']


def test_types_limit_and_abstention(built,tmp_path):
    data,directory,encoder,records,_=built
    assert HybridBackend(directory,encoder=encoder).search(req('zxq absent')).results==[]
    assert HybridBackend(directory,encoder=encoder).search(req('laser',entity_type='person')).results==[]
    many=[record('x'+str(i),eid='ent_x'+str(i)) for i in range(16)]
    other=tmp_path/'many'; build_index(many,other,encoder)
    result=HybridBackend(current_generation(other)[0],encoder=encoder).search(req())
    assert len(result.results)==10
    assert len({x.entity_id for x in result.results})==10
    assert [x.rank for x in result.results]==list(range(1,11))


def test_build_reuse_never_reencodes(built):
    data,directory,encoder,records,manifest=built
    def fail(*a,**kw): raise AssertionError('encoder called during cache reuse')
    encoder.encode_windows=fail
    assert build_index(records,data,encoder)['reused']
    assert current_generation(data)[1]['generation']==manifest['generation']


def test_failed_rebuild_preserves_ready(built):
    data,directory,encoder,records,manifest=built
    old=(data/'READY').read_bytes()
    def fail(*a,**kw): raise RuntimeError('synthetic embedding failure')
    encoder.encode_windows=fail
    with pytest.raises(RuntimeError): build_index(records+[record('c')],data,encoder)
    assert (data/'READY').read_bytes()==old
    assert not list((data/'indexes').glob('*.building'))
    assert HybridBackend(directory,encoder=FixtureEncoder(encoder.root)).search(req()).results


def test_retired_entities_and_empty_rebuild_leave_no_live_results(built):
    data,directory,encoder,records,_=built
    for item in records: item['entities'][0].status='retired'
    build_index(records,data,encoder)
    new_directory,_=current_generation(data)
    assert new_directory!=directory
    assert HybridBackend(new_directory,encoder=encoder).search(req()).results==[]


def test_fresh_process_keyword_restart_without_network(built):
    data,directory,encoder,records,_=built
    code='''import socket,sys
from app.search.backend import HybridBackend
from app.contracts import SearchRequest
def fail(*a,**kw): raise AssertionError('network forbidden')
socket.socket=fail
r=HybridBackend(sys.argv[1],mode='keyword').search(SearchRequest(schema_version='1',query='laser',revision=1))
assert r.results[0].entity_id=='ent_a'
print('persisted keyword index reused without network')
'''
    p=subprocess.run([sys.executable,'-c',code,str(directory)],capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    assert 'reused without network' in p.stdout


def test_missing_model_keeps_keyword_available(built):
    data,directory,encoder,records,_=built
    for p in (directory/'model').iterdir(): p.unlink()
    response=HybridBackend(directory).search(req())
    assert response.results[0].entity_id=='ent_a'
    assert any('embedding model unavailable' in x for x in response.limitations)


def test_corrupt_index_rejected(built):
    data,directory,encoder,records,_=built
    with (directory/'vectors.npy').open('ab') as f: f.write(b'corruption')
    with pytest.raises(ValueError,match='asset_hash'): HybridBackend(directory,encoder=encoder)
    with pytest.raises(ValueError,match='hash_mismatch'): build_index(records,data,encoder)


def test_supported_claims_aliases_and_missing_evidence(tmp_path):
    r=record(); old=r['entities'][0]
    resolved=old.model_copy(update={'entity_id':'ent_resolved','alias_entity_ids':[old.entity_id],
                                  'claim_ids':['clm_valid','clm_qualified','clm_contact'],'resolution_state':'confirmed'})
    pair=EvidencePair(version_id=r['version'].version_id,sentence_id=r['sentences'][0].sentence_id)
    claims=[Claim(schema_version='1',claim_id='clm_valid',subject_entity_id='ent_resolved',predicate='expertise',value='Precision instruments',evidence=[pair],support='supported'),
            Claim(schema_version='1',claim_id='clm_qualified',subject_entity_id='ent_resolved',predicate='role',value='A conditional role',evidence=[pair],support='qualified',qualification='Not current'),
            Claim(schema_version='1',claim_id='clm_contact',subject_entity_id='ent_resolved',predicate='official_contact',value='public@example.invalid',evidence=[pair],support='supported')]
    encoder=FixtureEncoder(tmp_path/'model'); data=tmp_path/'data'
    build_index([r],data,encoder,extra_entities=[resolved],claims=claims)
    result=HybridBackend(current_generation(data)[0],encoder=encoder).search(req()).results[0]
    assert result.entity_id=='ent_resolved'
    assert result.fields['expertise'][0].value=='Precision instruments'
    assert 'role' not in result.fields and 'official_contact' not in result.fields
    claims[0].evidence=[EvidencePair(version_id=r['version'].version_id,sentence_id=make_sentence_id(r['version'].version_id,999))]
    manifest=build_index([r],data,encoder,extra_entities=[resolved],claims=claims)
    assert any(x['reason']=='unavailable_claim_evidence' for x in manifest['knowledge']['withheld'])
    result=HybridBackend(current_generation(data)[0],encoder=encoder).search(req()).results[0]
    assert 'expertise' not in result.fields


def test_api_auto_loads_disk_backend_and_preserves_errors(built,monkeypatch):
    from app.main import app
    from app.api.search import set_backend
    data,directory,encoder,records,_=built
    set_backend(None)
    monkeypatch.delenv('BERNMATCH_FIXTURE_MODE',raising=False)
    monkeypatch.setenv('BERNMATCH_DATA_DIR',str(data))
    client=TestClient(app)
    try:
        response=client.post('/api/v1/search',json=req().model_dump())
        assert response.status_code==200
        assert response.json()['results'][0]['entity_id']=='ent_a'
        assert 'request_total' in response.json()['timing_ms']
        assert client.post('/api/v1/search',json=req('x'*2001).model_dump()).status_code==413
        (data/'READY').unlink()
        assert client.post('/api/v1/search',json=req().model_dump()).status_code==503
        (data/'READY').write_text('')
        assert client.post('/api/v1/search',json=req().model_dump()).status_code==501
        monkeypatch.setenv('BERNMATCH_FIXTURE_MODE','1')
        assert client.post('/api/v1/search',json=req().model_dump()).status_code==200
    finally: set_backend(None)


def test_freshness_uses_source_dates_never_fetch_alone():
    e={'content_date':None,'last_modified':None,'fetched_at':'2026-10-18T12:00:00Z'}
    assert freshness([e])=='unknown'
    assert freshness([e|{'content_date':'2001-01-01'}])=='stale'


def test_prolific_entity_cannot_sum_weak_keyword_pages(tmp_path):
    encoder=FixtureEncoder(tmp_path/'model')
    a=record('a',text='Laser instrument research.')
    b=record('b',text='Laser precision methods for laser precision instrumentation.')
    for label,records in [('baseline',[a,b]),('duplicated',[a,b]+[record('dup'+str(i),text='Laser instrument research.',eid='ent_a') for i in range(60)])]:
        data=tmp_path/label
        build_index(records,data,encoder)
        results=HybridBackend(current_generation(data)[0],mode='keyword').search(req('laser precision')).results
        assert results[0].entity_id=='ent_b'
        assert len([x for x in results if x.entity_id=='ent_a'])<=1


def test_real_tokenizer_overflow_pooling_and_prefix_plumbing(tmp_path,monkeypatch):
    import onnxruntime as ort
    from tokenizers import Tokenizer,models,pre_tokenizers
    from types import SimpleNamespace
    from app.search.encoder import OnnxEncoder,digest
    root=tmp_path/'onnx'; root.mkdir()
    tokenizer=Tokenizer(models.WordLevel({'[UNK]':0,'[PAD]':1,'passage':2,':':3,'word':4},unk_token='[UNK]'))
    tokenizer.pre_tokenizer=pre_tokenizers.Whitespace()
    tokenizer.save(str(root/'tokenizer.json'))
    (root/'config.json').write_text(json.dumps({'pad_token_id':1}))
    (root/'model.onnx').write_bytes(b'SYNTHETIC only')
    (root/'model_manifest.json').write_text(json.dumps({'repo':'synthetic/test-only','revision':'0'*40,'license':'mit',
        'files':{name:{'sha256':digest(root/name)} for name in ['model.onnx','tokenizer.json','config.json']}}))
    seen=[]
    class Session:
        def __init__(self,*a,**kw): pass
        def get_inputs(self): return [SimpleNamespace(name=k) for k in ['input_ids','attention_mask','token_type_ids']]
        def get_outputs(self): return [SimpleNamespace(shape=['batch','seq',2])]
        def run(self,unused,inputs):
            seen.append(inputs)
            out=np.zeros((*inputs['input_ids'].shape,2),dtype=np.float32)
            out[:,:,0]=1
            out[inputs['attention_mask']==0,1]=10000
            return [out]
    monkeypatch.setattr(ort,'InferenceSession',Session)
    encoder=OnnxEncoder(root)
    vectors,owners=encoder.encode_windows(['word '*1100,'word'])
    assert owners.tolist()==[0,0,0,1]
    assert np.allclose(vectors,np.tile([1,0],(4,1)))
    assert max(x['input_ids'].shape[1] for x in seen)<=512
    assert seen[0]['input_ids'][0,:2].tolist()==[2,3]


def test_export_adapter_preserves_shared_records(tmp_path):
    from app.search.__main__ import read_export
    r=record()
    payload={k:[v.model_dump() for v in value] if isinstance(value,list) and value and hasattr(value[0],'model_dump')
             else value.model_dump() if hasattr(value,'model_dump') else value for k,value in r.items()}
    path=tmp_path/'export.jsonl'; path.write_text(json.dumps(payload)+'\n')
    loaded=read_export(path)[0]
    assert loaded['version']==r['version']
    assert loaded['sentences']==r['sentences']
    assert loaded['passage_entity_ids']==r['passage_entity_ids']


def test_model_download_is_pinned_bounded_and_atomic(tmp_path,monkeypatch):
    import httpx
    import app.search.models as download
    from app.search.encoder import digest
    content=b'synthetic model bytes'
    asset={'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content),'source_path':'weights.onnx'}
    pin={'repo':'synthetic/test-only','revision':'0'*40,'files':{'model.onnx':asset}}
    config=tmp_path/'pins.json'; config.write_text(json.dumps({'small':pin}))
    original_path=download.Path
    class PinPath(type(Path())):
        def with_name(self,name): return config if name=='models.json' else super().with_name(name)
    monkeypatch.setattr(download,'Path',PinPath)
    real_client=httpx.Client
    monkeypatch.setattr(download.httpx,'Client',lambda **kw:real_client(transport=httpx.MockTransport(lambda req:httpx.Response(200,content=content)),**kw))
    destination=tmp_path/'good'
    download.fetch_model('small',destination)
    assert digest(destination/'model.onnx')==asset['sha256']
    # Matching cached assets must not make another request.
    monkeypatch.setattr(download.httpx,'Client',lambda **kw:(_ for _ in ()).throw(AssertionError('network called')))
    download.fetch_model('small',destination)
    monkeypatch.setattr(download.httpx,'Client',lambda **kw:real_client(transport=httpx.MockTransport(lambda req:httpx.Response(200,content=content+b'overflow')),**kw))
    with pytest.raises(ValueError,match='size_mismatch'): download.fetch_model('small',tmp_path/'bad')
    assert not (tmp_path/'bad').exists()
    assert not list(tmp_path.glob('.e5-download-*'))


def test_entity_alias_change_reuses_vectors_but_changes_evidence_metadata(built):
    data,directory,encoder,records,_=built
    r=records[0]
    old=r['entities'][0]
    merged=old.model_copy(update={'entity_id':'ent_resolved','alias_entity_ids':['ent_a']})
    def fail(*a,**kw): raise AssertionError('unchanged public text was re-encoded')
    encoder.encode_windows=fail
    manifest=build_index(records,data,encoder,extra_entities=[merged])
    assert manifest['reused_windows']>0 and manifest['encoded_entries']==0
    backend=HybridBackend(current_generation(data)[0],encoder=FixtureEncoder(encoder.root))
    assert backend.search(req()).results[0].entity_id=='ent_resolved'


def test_live_suppression_matches_alias_before_ranking(built,tmp_path,monkeypatch):
    data,directory,encoder,records,_=built
    resolved=records[0]['entities'][0].model_copy(update={'entity_id':'ent_canonical','alias_entity_ids':['ent_a']})
    build_index(records,data,encoder,extra_entities=[resolved])
    policy=tmp_path/'suppression.json'
    policy.write_text(json.dumps({'schema_version':'1','entries':[{'entry_id':'fixture-removal',
        'reason_category':'removal_request','action':'suppress','confirmed_at':'2026-10-18T12:00:00Z',
        'confirmed_by_role':'test operator','identifiers':{'entity_ids':['ent_a']}}]}))
    monkeypatch.setenv('BERNMATCH_SUPPRESSION_FILE',str(policy))
    response=HybridBackend(current_generation(data)[0],encoder=encoder).search(req())
    assert not any(x.entity_id=='ent_canonical' for x in response.results)


def test_query_bundle_preserves_exact_evidence_route(built,tmp_path,monkeypatch):
    import tarfile
    from app.search.bundle import package_bundle
    from app.main import app
    data,directory,encoder,records,_=built
    output=tmp_path/'search.tar.gz'
    report=package_bundle(data,output)
    assert report['archive_bytes']==output.stat().st_size
    extracted=tmp_path/'query-only'; extracted.mkdir()
    with tarfile.open(output) as archive:
        archive.extractall(extracted,filter='data')
    assert (extracted/'corpus.sqlite').is_symlink()
    assert (extracted/'corpus.sqlite').resolve().is_relative_to(extracted)
    assert current_generation(extracted)[1]['fingerprint']==current_generation(data)[1]['fingerprint']
    monkeypatch.setenv('BERNMATCH_DATA_DIR',str(extracted))
    sentence=records[0]['sentences'][0]
    with TestClient(app) as client:
        response=client.get(f'/api/v1/evidence/{sentence.version_id}/{sentence.sentence_id}')
        assert response.status_code==200
        assert response.json()['text']==sentence.text
        assert client.get(f'/api/v1/evidence/wrong-version/{sentence.sentence_id}').status_code==410
