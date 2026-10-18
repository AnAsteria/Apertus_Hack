"""Meaningful deterministic T06 checks. Real network smoke tests are opt-in CLI jobs."""
from io import BytesIO
import json
from pathlib import Path
import httpx
import pytest

pytest.importorskip('protego', reason='Install app/ingest/requirements.txt for the ingestion suite')
pytest.importorskip('yaml', reason='Install app/ingest/requirements.txt for the ingestion suite')
pytest.importorskip('bs4', reason='Install app/ingest/requirements.txt for the ingestion suite')
pytest.importorskip('langdetect', reason='Install app/ingest/requirements.txt for the ingestion suite')
pytest.importorskip('pypdf', reason='Install app/ingest/requirements.txt for the ingestion suite')

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from app.contracts import SourceConfig, content_hash
from app.ingest.types import Source, Fetched, IngestError
from app.ingest.network import Fetcher, canonical_url, in_scope, public_addresses
from app.ingest.extract import parse, language, PARSER_VERSION
from app.ingest.pipeline import crawl
from app.ingest.config import generate_registry, load_source
from app.storage.corpus import CorpusStore


def source(max_pages=5):
    return Source(config=SourceConfig(schema_version='1', source_id='test', label='Test',
        start_urls=['https://example.org/research/'], allowed_domains=['example.org'],
        allowed_paths=['/research/'], languages=['en','de','fr','it'], max_pages=max_pages,
        max_depth=2, requests_per_second=.5, focus_areas=['diabetes']), labels=['unibe'],
        tier='focus', profile='dev')


def fetched(html, url='https://example.org/research/', media='text/html'):
    return Fetched(url,url,html.encode() if isinstance(html,str) else html,media,'2026-10-18T12:00:00Z')


HTML = '<html lang="en"><title>Research Group</title><body><nav>Discard navigation</nav><main><h1>Research Group</h1><p>We develop glucose sensors for diabetes research. We study reliable devices.</p></main><footer>Dynamic footer 1</footer></body></html>'


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler),follow_redirects=False)


class Clock:
    def __init__(self): self.now=0.;self.waits=[]
    def time(self): return self.now
    def sleep(self,n): self.waits.append(n);self.now+=n


def test_url_normalisation_and_strict_scope():
    assert canonical_url('HTTPS://Example.Org:443/research/?utm_x=1&b=2&a=3#x') == 'https://example.org/research/?a=3&b=2'
    assert not in_scope('https://example.org.evil.test/research/',source())
    assert not in_scope('https://example.org/research-private/',source())
    assert not in_scope('https://user:secret@example.org/research/',source())
    with pytest.raises(IngestError,match='private_or_nonpublic'):
        public_addresses('127.0.0.1')


def test_robots_wildcards_terminal_and_merged_groups():
    calls=[]
    robots='User-agent: *\nDisallow: /research/*?preview$\n\nUser-agent: *\nDisallow: /research/private/\nAllow: /research/private/public$\n'
    def handler(req):
        calls.append(str(req.url));return httpx.Response(200,text=robots if req.url.path=='/robots.txt' else HTML)
    fetch=Fetcher(client_for(handler),resolver=lambda h: ['93.184.216.34'],sleep=lambda n:None)
    with pytest.raises(IngestError,match='robots_disallowed'): fetch.fetch('https://example.org/research/a?preview',source())
    with pytest.raises(IngestError,match='robots_disallowed'): fetch.fetch('https://example.org/research/private/a',source())
    assert fetch.fetch('https://example.org/research/private/public',source()).body
    assert 'https://example.org/research/private/a' not in calls
    assert calls.count('https://example.org/robots.txt')==1


def test_redirect_scope_and_target_robots_checked_before_request():
    calls=[]
    def handler(req):
        calls.append(str(req.url))
        if req.url.path=='/robots.txt':return httpx.Response(200,text='User-agent: *\nDisallow: /research/blocked')
        return httpx.Response(302,headers={'location':'/research/blocked'})
    fetch=Fetcher(client_for(handler),resolver=lambda h: [],sleep=lambda n:None)
    with pytest.raises(IngestError,match='robots_disallowed'):fetch.fetch('https://example.org/research/',source())
    assert 'https://example.org/research/blocked' not in calls
    def outside(req):
        return httpx.Response(404) if req.url.path=='/robots.txt' else httpx.Response(302,headers={'location':'https://evil.test/research/'})
    with pytest.raises(IngestError,match='outside_scope'):
        Fetcher(client_for(outside),resolver=lambda h:[],sleep=lambda n:None).fetch('https://example.org/research/',source())


def test_robots_fail_closed_retry_and_rate_limit():
    clock=Clock();calls=[]
    def handler(req):
        calls.append(str(req.url));return httpx.Response(503)
    fetch=Fetcher(client_for(handler),resolver=lambda h:[],sleep=clock.sleep,clock=clock.time)
    with pytest.raises(IngestError,match='robots_unavailable'):fetch.fetch('https://example.org/research/',source())
    assert len(calls)==3 and fetch.retries==2
    assert all(u.endswith('/robots.txt') for u in calls)
    assert clock.now>=4


def test_response_size_bound():
    def handler(req):return httpx.Response(404) if req.url.path=='/robots.txt' else httpx.Response(200,content=b'x'*100)
    spec=source();spec.max_bytes=20
    with pytest.raises(IngestError,match='response_too_large'):
        Fetcher(client_for(handler),resolver=lambda h:[],sleep=lambda n:None).fetch(spec.config.start_urls[0],spec)


def test_clean_text_hash_and_immutable_versions(tmp_path):
    store=CorpusStore(tmp_path)
    page=fetched(HTML);parsed=parse(page)
    first,reused=store.ingest('test',['unibe','artorg'],page,parsed,PARSER_VERSION)
    assert not reused
    altered=fetched(HTML.replace('footer 1','footer 2').replace('<main>','<main class="changed">'))
    second,reused=store.ingest('test',['unibe'],altered,parse(altered),PARSER_VERSION)
    assert reused and first.version_id==second.version_id
    changed=fetched(HTML.replace('glucose sensors','insulin pumps'))
    third,reused=store.ingest('test',['unibe'],changed,parse(changed),PARSER_VERSION)
    assert not reused and third.version_id!=first.version_id
    sid=first.passages[0].sentence_ids[-1]
    original=store.get_sentence(first.version_id,sid)
    assert original.text in parsed.text and 'footer' not in parsed.text
    with pytest.raises(KeyError):store.get_sentence(third.version_id,sid)
    reopened=CorpusStore(tmp_path)
    assert reopened.get_sentence(first.version_id,sid).text==original.text
    active=reopened.active_records()
    assert len(active)==1 and active[0]['version'].version_id==third.version_id
    assert all(e.resolution_state=='uncertain' and not e.claim_ids for e in active[0]['entities'])
    with reopened.connect() as db:assert db.execute('SELECT count(*) FROM labels').fetchone()[0]==2


def test_language_variants_stay_separate_and_linked(tmp_path):
    store=CorpusStore(tmp_path)
    en=fetched(HTML.replace('<main>','<link rel="alternate" hreflang="de" href="/research/de"><main>'))
    de=fetched(HTML.replace('lang="en"','lang="de"').replace('Research Group','Forschungsgruppe'),url='https://example.org/research/de')
    for page in (en,de):store.ingest('test',['unibe'],page,parse(page),PARSER_VERSION)
    store.link_variants();records=store.active_records()
    assert len(records)==2 and {r['version'].language for r in records}=={'en','de'}
    assert all(len(r['document'].language_variant_document_ids)==1 for r in records)


def pdf_bytes(text=True):
    writer=PdfWriter()
    for value in ('Glucose sensing research.','Insulin technology research.'):
        page=writer.add_blank_page(width=300,height=200)
        if text:
            font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
            stream=DecodedStreamObject();stream.set_data(f'BT /F1 12 Tf 20 100 Td ({value}) Tj ET'.encode())
            page[NameObject('/Contents')]=writer._add_object(stream)
    out=BytesIO();writer.write(out);return out.getvalue()


def test_pdf_text_page_numbers_and_scanned_reporting(tmp_path):
    page=fetched(pdf_bytes(),media='application/pdf');parsed=parse(page)
    assert [s.page_number for s in parsed.sections]==[1,2]
    assert '\f' in parsed.text
    store=CorpusStore(tmp_path);v,_=store.ingest('test',['unibe'],page,parsed,PARSER_VERSION)
    sentences=store.active_records()[0]['sentences']
    assert {s.page_number for s in sentences}=={1,2}
    assert all(s.text in parsed.text for s in sentences)
    with pytest.raises(IngestError,match='scanned_or_empty_pdf'):
        parse(fetched(pdf_bytes(False),media='application/pdf'))


@pytest.mark.parametrize('expected,text',[
 ('en','The research group develops medical devices and studies new methods for the treatment of disease in patients.'),
 ('de','Unsere Forschungsgruppe entwickelt medizinische Geräte und untersucht neue Methoden zur Behandlung von Krankheiten.'),
 ('fr','Notre groupe de recherche développe des dispositifs médicaux et étudie de nouvelles méthodes pour traiter les maladies.'),
 ('it','Il nostro gruppo di ricerca sviluppa dispositivi medici e studia nuovi metodi per il trattamento delle malattie.')])
def test_local_language_detection(expected,text):assert language(text)==expected


def test_sitemap_bounds_restart_and_no_network_on_reuse(tmp_path):
    calls=[]
    def handler(req):
        calls.append(str(req.url))
        if req.url.path=='/robots.txt':return httpx.Response(200,text='User-agent: *\nAllow: /\nSitemap: https://example.org/research/map.xml')
        if req.url.path.endswith('map.xml'):return httpx.Response(200,text='<urlset><url><loc>https://example.org/research/second</loc></url><url><loc>https://elsewhere.test/x</loc></url></urlset>')
        return httpx.Response(200,text=HTML,headers={'content-type':'text/html'})
    store=CorpusStore(tmp_path);fetch=Fetcher(client_for(handler),resolver=lambda h:[],sleep=lambda n:None)
    report=crawl(source(2),store,fetch)
    assert report['counts']['fetched']==2 and len(store.active_records())==2
    assert not any('elsewhere.test' in u for u in calls)
    def forbidden(req):pytest.fail('Restart must reuse stored pages without HTTP requests')
    reused=crawl(source(2),CorpusStore(tmp_path),Fetcher(client_for(forbidden),resolver=lambda h:[]))
    assert reused['counts']['network_requests']==0
    # Cached discovery must preserve sitemap-discovered URLs as well as anchor links.
    assert reused['counts']['reused']==2


def test_budget_is_config_not_hidden_constant(tmp_path):
    def handler(req):
        if req.url.path=='/robots.txt':return httpx.Response(404)
        return httpx.Response(200,text=HTML.replace('</main>','<a href="/research/next">Next</a></main>'),headers={'content-type':'text/html'})
    report=crawl(source(1),CorpusStore(tmp_path),Fetcher(client_for(handler),resolver=lambda h:[],sleep=lambda n:None))
    assert report['counts']['fetched']==1 and report['source_config']['max_pages']==1
    assert report['counts']['remaining_discovered']==1


def test_inventory_registry_join_and_profiles(tmp_path):
    import shutil
    directory=Path(__file__).parents[2]/'config/sources'
    for name in ('unibe_inventory.csv','unibe_inventory_audit.csv','crawl_profiles.json','discovery_seeds.json'):
        shutil.copyfile(directory/name,tmp_path/name)
    paths=generate_registry(tmp_path)
    assert len(paths)==41
    assert json.loads((tmp_path/'generated/excluded.json').read_text())[0]['inventory_key']=='geo2.unibe.ch'
    path=tmp_path/'generated/artorg.yaml'
    assert load_source(path,'dev').config.max_pages==20
    assert load_source(path,'final').config.max_pages==200
    assert load_source(path,'dev',3).config.max_pages==3
    assert load_source(path,'dev').labels==['unibe','artorg']


def test_tracking_query_cannot_bypass_robots():
    seen=[]
    def handler(req):
        seen.append(str(req.url))
        if req.url.path=='/robots.txt':
            return httpx.Response(200,text='User-agent: *\nDisallow: /*utm_source=blocked$')
        return httpx.Response(200,text=HTML)
    fetch=Fetcher(client_for(handler),resolver=lambda h:[],sleep=lambda n:None)
    with pytest.raises(IngestError,match='robots_disallowed'):
        fetch.fetch('https://example.org/research/?utm_source=blocked',source())
    assert len(seen)==1


def test_directory_group_routing_and_wordpress_related_content():
    from app.ingest.extract import classify
    assert classify('https://www.artorg.unibe.ch/research/aihn/index_eng.html','AI in Health and Nutrition',[])=='unit'
    assert classify('https://www.dcberne.com/en/projects/','Research - Diabetes Center Berne',[])=='directory'
    html='<html lang="en"><body><ul class="et_pb_social_media_follow"><li>Social noise</li></ul><div id="main-content"><article><h1>Sensor project</h1><p>We research novel glucose sensor technology for diabetes.</p><article><h2>Unrelated project</h2><p>Never attribute this capability to the main project.</p></article></article></div></body></html>'
    result=parse(fetched(html,url='https://example.org/en/project/sensor/'))
    assert 'Unrelated project' not in result.text and 'Social noise' not in result.text


def test_temporary_refresh_failure_preserves_active_evidence(tmp_path):
    store=CorpusStore(tmp_path);page=fetched(HTML)
    old,_=store.ingest('test',['unibe'],page,parse(page),PARSER_VERSION)
    def handler(req):return httpx.Response(404) if req.url.path=='/robots.txt' else httpx.Response(503)
    report=crawl(source(1),store,Fetcher(client_for(handler),resolver=lambda h:[],sleep=lambda n:None),refresh=True)
    assert report['counts']['failed']==1
    assert store.active_records()[0]['version'].version_id==old.version_id


def test_unsupported_content_is_reported_with_raw_provenance(tmp_path):
    blank=pdf_bytes(False)
    def handler(req):
        if req.url.path=='/robots.txt':return httpx.Response(404)
        return httpx.Response(200,content=blank,headers={'content-type':'application/pdf'})
    store=CorpusStore(tmp_path)
    report=crawl(source(1),store,Fetcher(client_for(handler),resolver=lambda h:[],sleep=lambda n:None))
    assert report['counts']['unsupported']==1
    assert report['events'][0]['reason']=='scanned_or_empty_pdf'
    observation=json.loads(next((tmp_path/'fetches').glob('*.json')).read_text())
    assert observation['version_id'] is None and observation['reason']=='scanned_or_empty_pdf'
    assert (tmp_path/'raw'/observation['raw_sha256']).read_bytes()==blank
    assert store.active_records()==[]


def test_directory_paper_titles_do_not_become_distinct_units(tmp_path):
    html='<html lang="en"><title>Research directory</title><main><h1>Research</h1><h2>Cancer Therapy Resistance - CTR</h2><p>We study treatment resistance in cancer.</p><h2>Unrelated publication title</h2><p>A paper reports some measured results with an example method.</p></main></html>'
    page=fetched(html,url='https://example.org/research/index_eng.html');store=CorpusStore(tmp_path)
    store.ingest('test',['unibe'],page,parse(page),PARSER_VERSION)
    names={e.name for e in store.active_records()[0]['entities']}
    assert 'Cancer Therapy Resistance - CTR' in names
    assert 'Unrelated publication title' not in names


def test_source_modification_date_is_distinct_from_fetch_date(tmp_path):
    html=HTML.replace('<title>','<meta property="article:modified_time" content="2025-05-12T10:00:00Z"><title>')
    page=fetched(html);parsed=parse(page);store=CorpusStore(tmp_path)
    version,_=store.ingest('test',['unibe'],page,parsed,PARSER_VERSION)
    assert version.last_modified=='2025-05-12T10:00:00Z'
    assert version.fetched_at=='2026-10-18T12:00:00Z'


def test_generated_registry_cannot_reenable_stale_excluded_yaml(tmp_path):
    import shutil
    from app.ingest.config import registry_paths
    directory=Path(__file__).parents[2]/'config/sources'
    for name in ('unibe_inventory.csv','unibe_inventory_audit.csv','crawl_profiles.json','discovery_seeds.json'):
        shutil.copyfile(directory/name,tmp_path/name)
    generate_registry(tmp_path)
    (tmp_path/'generated/stale-excluded.yaml').write_text('not: an active source')
    paths=registry_paths(tmp_path)
    assert len(paths)==41
    assert all(p.name!='stale-excluded.yaml' for p in paths)


def test_people_directory_is_not_a_named_person():
    from app.ingest.extract import classify
    assert classify('https://example.org/people/index_eng.html','People',[])=='directory'
    assert classify('https://example.org/people/example/index_eng.html','Example Researcher',[])=='person'
