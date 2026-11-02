"""Offline, loopback SYNTHETIC demo. No installation, scheduled task or real data."""
from pathlib import Path
import argparse,json,os,secrets,subprocess,sys,time,urllib.parse,urllib.request


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--package-root',required=True)
    parser.add_argument('command',choices=('prepare','start','check','stop'))
    args=parser.parse_args();root=Path(args.package_root).resolve()
    source=root/'source';runtime=root/'runtime/windows';state_dir=root/'demo';state_dir.mkdir(exist_ok=True)
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    python=runtime/'venv/Scripts/python.exe'
    environment=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    def run(arguments):
        with (state_dir/'setup.log').open('ab') as log:
            subprocess.run([str(x) for x in arguments],cwd=source,env=environment,creationflags=flags,stdout=log,stderr=log,check=True)
    def prepare():
        longest=runtime/'venv/Lib/site-packages/torch/include/ATen/native/transformers/cuda/mem_eff_attention/iterators/predicated_tile_access_iterator_residual_last.h'
        if os.name=='nt' and len(str(longest))>=259:
            raise ValueError('Unpack the package to a short path, for example D:\\VS01; Windows wheel paths exceed MAX_PATH here')
        if not python.is_file():run([runtime/'python/python.exe','-m','venv',runtime/'venv'])
        if not (state_dir/'dependencies.ready').exists():
            run([python,'-m','pip','install','--no-index','--disable-pip-version-check','--find-links',root/'wheelhouse-windows','--require-hashes','-r',source/'services/visual_search/requirements-windows.lock'])
            (state_dir/'dependencies.ready').write_text('hash-locked offline install\n')
        if not (state_dir/'synthetic/DATA_CLASS.txt').is_file():
            run([python,'-m','services.visual_search.synthetic','--root',state_dir/'synthetic','--model',root/'model'])
    if args.command=='prepare':prepare();return
    if args.command=='start':
        prepare()
        if (state_dir/'pids.json').is_file():
            sys.path.insert(0,str(runtime/'venv/Lib/site-packages'))
            import psutil
            for pid in json.loads((state_dir/'pids.json').read_text()):
                try:
                    if str(state_dir) in ' '.join(psutil.Process(pid).cmdline()):
                        print('Demo already started: http://127.0.0.1:18986/static/search.html');return
                except psutil.NoSuchProcess:pass
        key=secrets.token_hex(32)
        worker={'key_hex':key,'index':str(state_dir/'synthetic/index'),'model':str(root/'model'),'port':18985}
        gateway={'key_hex':key,'origin':'http://127.0.0.1:18986','worker_url':'http://127.0.0.1:18985','synthetic_lab':True,'enabled':True,'synthetic_root':str(state_dir/'synthetic'),'port':18986}
        for name,value in [('worker',worker),('gateway',gateway)]:
            (state_dir/(name+'.json')).write_text(json.dumps(value),'utf-8')
        processes=[]
        for module,rest in [('services.visual_search.run',['worker','--config',state_dir/'worker.json']),('services.visual_search.lab',['--config',state_dir/'gateway.json'])]:
            log=(state_dir/(module.rsplit('.',1)[-1]+'.log')).open('ab')
            processes.append(subprocess.Popen([str(python),'-B','-m',module]+[str(x) for x in rest],cwd=source,env=environment,creationflags=flags,stdout=log,stderr=log))
        (state_dir/'pids.json').write_text(json.dumps([p.pid for p in processes]),'utf-8')
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(150):
            try:
                with opener.open('http://127.0.0.1:18985/health',timeout=1) as response:
                    if json.load(response)['ready']:break
            except OSError:pass
            time.sleep(.1)
        else:raise RuntimeError('demo_not_ready_see_demo_logs')
        print('SYNTHETIC demo: http://127.0.0.1:18986/static/search.html')
    elif args.command=='check':
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        url='http://127.0.0.1:18986/api/visual-search/search?product_type='+urllib.parse.quote('Тестовый вид А')
        request=urllib.request.Request(url,data=(state_dir/'synthetic/images/97000.jpg').read_bytes(),headers={'Cookie':'session=SYNTHETIC','Origin':'http://127.0.0.1:18986','Content-Type':'image/jpeg'})
        with opener.open(request,timeout=10) as response:result=json.load(response)
        assert result['total']>=55 and result['api_version']==1
        print(json.dumps({'pass':True,'data_class':'SYNTHETIC','returned_codes':result['total'],'ranking':result['ranking_version']}))
    elif args.command=='stop':
        sys.path.insert(0,str(runtime/'venv/Lib/site-packages'))
        import psutil
        if not (state_dir/'pids.json').is_file():return
        owned=[]
        for pid in json.loads((state_dir/'pids.json').read_text()):
            try:
                process=psutil.Process(pid)
                command=' '.join(process.cmdline())
                if str(state_dir) not in command or 'services.visual_search.' not in command:continue
                owned.extend(process.children(recursive=True));owned.append(process)
            except psutil.NoSuchProcess:continue
        for process in reversed(owned):
            try:process.terminate()
            except psutil.NoSuchProcess:pass
        print('Only the synthetic demo processes stopped')


if __name__=='__main__':main()
