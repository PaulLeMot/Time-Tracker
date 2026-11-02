"""Faults only in the explicitly identified loopback SYNTHETIC lab."""
from pathlib import Path
import argparse,asyncio,json,ssl,sys,time
import httpx,psutil

async def main(root):
    root=Path(root).resolve();state=json.loads((root/'lab_state.json').read_text())
    gateway=json.loads((root/'gateway_private.json').read_text());worker_base=gateway['worker_url']
    verify=ssl.create_default_context(cafile=gateway['ca_file']) if gateway.get('ca_file') else True
    client=httpx.AsyncClient(base_url='http://127.0.0.1:18982',verify=verify,trust_env=False,timeout=10,headers={'Cookie':'session=SYNTHETIC','Origin':'http://127.0.0.1:18982'})
    assert (await client.get('/lab/status')).json()['data_class']=='SYNTHETIC'
    caps=(await client.get('/api/visual-search/capabilities')).json()
    kind=caps['product_types'][0];body=(root/'synthetic/images/97000.jpg').read_bytes()
    async def search():
        return await client.post('/api/visual-search/search',params={'product_type':kind},headers={'Content-Type':'image/jpeg'},content=body)
    responses=await asyncio.gather(*[search() for _ in range(4)])
    statuses=[r.status_code for r in responses]
    assert statuses.count(200)==3 and statuses.count(429)==1,statuses
    first=next(r.json() for r in responses if r.status_code==200)
    page=await client.get('/api/visual-search/results',params={'cursor':first['cursor'],'offset':30})
    assert page.status_code==200 and len(page.json()['items'])>0
    # Direct worker cursor is bound to the authenticated subject, not a bearer token alone.
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from services.visual_search.protocol import signed
    config=json.loads((root/'worker_private.json').read_text());key=bytes.fromhex(config['key_hex'])
    path='/v1/results?cursor='+first['cursor']+'&offset=30'
    wrong=await client.get(worker_base+path,headers=signed(key,'GET',path,'999999'))
    assert wrong.status_code==410
    def compute_process():
        owned=[]
        for pid in state['pids']:
            parent=psutil.Process(pid)
            command=' '.join(parent.cmdline())
            if 'services.visual_search.run' in command:
                owned.extend(parent.children(recursive=True))
        matches=[p for p in owned if p.name().lower()=='pythonw.exe' and 'spawn_main' in ' '.join(p.cmdline())]
        assert len(matches)==1,[(p.pid,p.name()) for p in matches]
        return matches[0]
    before=compute_process();before.terminate()
    started=time.monotonic()
    for _ in range(150):
        await asyncio.sleep(.1)
        r=await client.get(worker_base+'/health')
        if r.status_code==200 and time.monotonic()-started>.7:break
    else:raise AssertionError('no crash recovery')
    assert compute_process().pid!=before.pid
    crash_recovery=time.monotonic()-started
    for _ in range(200):
        response=await search()
        if response.status_code==200:break
        await asyncio.sleep(.1)
    else:raise AssertionError('gateway did not recover')
    # A hung native process is terminated after the deadline; recovery is independent.
    hung=compute_process();hung.suspend();started=time.monotonic()
    response=await search();deadline=time.monotonic()-started
    print(json.dumps({'fault_stage':'hung_response','status':response.status_code,'seconds':deadline}),flush=True)
    if deadline < 6:
        # A transient 503 after process recovery is allowed, but is not a timeout test.
        hung.resume()
        await asyncio.sleep(1)
        assert (await search()).status_code==200
        hung=compute_process();hung.suspend();started=time.monotonic()
        response=await search();deadline=time.monotonic()-started
    assert response.status_code in (503,504),response.status_code
    assert deadline<8.5,deadline
    for _ in range(150):
        await asyncio.sleep(.1)
        if (await client.get(worker_base+'/health')).status_code==200:break
    else:raise AssertionError('no timeout recovery')
    assert not psutil.pid_exists(hung.pid)
    assert (await search()).status_code==200
    await client.aclose()
    print(json.dumps({'pass':True,'admission_statuses':statuses,'metadata_pagination':True,'subject_isolation':True,'crash_recovery_seconds':crash_recovery,'hung_request_seconds':deadline,'no_orphan_compute':True}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--work-root',required=True);args=parser.parse_args()
    try:asyncio.run(main(args.work_root))
    finally:
        state=json.loads((Path(args.work_root)/'lab_state.json').read_text())
        for pid in state['pids']:
            if not psutil.pid_exists(pid):continue
            for child in psutil.Process(pid).children(recursive=True):
                if child.name().lower()=='pythonw.exe' and child.status()==psutil.STATUS_STOPPED:
                    child.resume()
