"""Atomic switch/rollback under live queries, only on a temporary SYNTHETIC index."""
from pathlib import Path
import argparse,json,os,secrets,shutil,sys,tempfile,time
import httpx
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.visual_search.engine import build
from services.visual_search.protocol import signed
from services.visual_search.worker import create_worker

def run(root,model):
    root=Path(root).resolve();assert (root/'DATA_CLASS.txt').read_text().strip()=='SYNTHETIC'
    key=secrets.token_bytes(32)
    with tempfile.TemporaryDirectory() as temporary:
        target=Path(temporary);shutil.copytree(root/'index',target/'index')
        pointer=target/'index/current.json';previous=pointer.read_bytes()
        old=json.loads(previous)['generation']
        app=create_worker({'key_hex':key.hex(),'index':str(target/'index'),'model':str(model)})
        with TestClient(app) as client:
            def request(method,path,body=b''):
                return client.request(method,path,content=body,headers=signed(key,method,path,'123',body)|({'Content-Type':'image/jpeg'} if body else {}))
            import urllib.parse
            path='/v1/search?'+urllib.parse.urlencode({'product_type':'Тестовый вид А'})
            body=(root/'images/97000.jpg').read_bytes()
            assert request('POST',path,body).status_code==200
            # Broken generation must not replace the current warmed index.
            pointer.write_text('{"generation":"index-0","sha256":"bad"}')
            time.sleep(.8)
            assert request('GET','/v1/capabilities').json()['index_version']==old
            rows=json.loads((root/'catalogue.json').read_text('utf-8'));rows=[r for r in rows if r['code']!='98000']
            catalogue=target/'catalogue.json';catalogue.write_text(json.dumps(rows,ensure_ascii=False),'utf-8')
            build(catalogue,root/'images',target/'index',model)
            new=json.loads(pointer.read_bytes())['generation'];statuses=[]
            def wait_for(version):
                deadline=time.monotonic()+20
                while time.monotonic()<deadline:
                    r=request('POST',path,body);statuses.append(r.status_code)
                    assert r.status_code==200,r.text
                    if r.json()['index_version']==version:return r.json()
                raise AssertionError('index promotion did not complete')
            switched=wait_for(new)
            temporary_pointer=pointer.with_suffix('.tmp');temporary_pointer.write_bytes(previous);os.replace(temporary_pointer,pointer)
            restored=wait_for(old)
            assert restored['total']==switched['total']+1
            print(json.dumps({'pass':True,'live_queries':len(statuses),'all_200':True,'corrupt_pointer_preserved_old':True,'warm_switch':True,'rollback':True}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--synthetic-root',required=True);parser.add_argument('--model',required=True);args=parser.parse_args()
    run(args.synthetic_root,args.model)
