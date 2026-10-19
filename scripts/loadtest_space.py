import time,math,json,statistics,concurrent.futures as cf,httpx,sys
BASE='https://kaktamsdengami-bern-match.hf.space/api/v1/search'
Q=['insulin pump algorithms','Krebsforschung Immuntherapie','robotic surgery instruments','microbiome antibiotic resistance',
   'Bildgebung Gehirn','stroke rehabilitation','sequencing platform','glucose sensor','cardiovascular fluid dynamics','epilepsy research']
def one(i):
    body={'schema_version':'1','query':Q[i%len(Q)],'revision':1}
    t=time.perf_counter()
    try:
        r=httpx.post(BASE,json=body,timeout=30)
        return r.status_code,(time.perf_counter()-t)*1000,(r.json().get('timing_ms') or {}).get('request_total') if r.status_code==200 else None
    except Exception as e:
        return 'ERR:'+type(e).__name__,(time.perf_counter()-t)*1000,None
for workers,total in ((1,10),(10,100)):
    t0=time.perf_counter()
    with cf.ThreadPoolExecutor(workers) as ex: res=list(ex.map(one,range(total)))
    wall=time.perf_counter()-t0
    ok=[r for r in res if r[0]==200]; lat=sorted(r[1] for r in ok); srv=sorted(r[2] for r in ok if r[2] is not None)
    nr=lambda a,p:a[math.ceil(p/100*len(a))-1] if a else None
    codes={}; [codes.__setitem__(str(r[0]),codes.get(str(r[0]),0)+1) for r in res]
    print(json.dumps({'concurrency':workers,'requests':total,'wall_s':round(wall,1),'throughput_rps':round(total/wall,2),'codes':codes,
      'client_ms_p50':round(nr(lat,50)),'client_ms_p95':round(nr(lat,95)),'server_ms_p50':round(nr(srv,50)),'server_ms_p95':round(nr(srv,95))}))
