import hashlib, io, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageDraw
from services.visual_search.views import profile, representations, safe_source, read_source
from services.visual_search.index2 import build,activate,atomic_json
from services.visual_search.engine import Engine,resolve_index
from services.visual_search.jobs2 import Jobs,execute
from services.visual_search.management2 import install
from services.visual_search.protocol import signed
from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace
from services.visual_search.worker import Runner
import asyncio,pickle


class FakeEmbedder:
    model_hash='synthetic-model'
    def __call__(self,image):
        # Deterministic image fingerprint for infrastructure tests, never quality evidence.
        a=np.asarray(image.resize((8,8)),dtype='float32').ravel();v=np.pad(a,(0,384-len(a)))
        return v/max(np.linalg.norm(v),1e-9)


class Stage2Tests(unittest.TestCase):
    def test_new_feature_batches_are_bounded_and_incremental(self):
        batches=[]
        class BatchEmbedder(FakeEmbedder):
            def batch(self,images):batches.append(len(images));return np.stack([self(image) for image in images])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);rows=[]
            for n in range(9):
                image=Image.new('RGB',(80,80),(20+n*20,20,100));image.save(root/(str(n)+'.png'))
                rows.append({'code':str(90000+n),'name':'SYN','product_type':'A','assets':[{'root':'r','relative':str(n)+'.png','id':str(n)}]})
            embed=BatchEmbedder();build(rows,{'r':folder},root/'index','unused',embedder=embed)
            self.assertEqual(batches,[8,1]);build(rows,{'r':folder},root/'index','unused',embedder=embed);self.assertEqual(batches,[8,1])

    def test_runner_transmits_serializable_command_not_async_task(self):
        sent=[]
        class Pipe:
            def send(self,message):pickle.dumps(message);sent.append(message)
            def recv(self):return ('ok',{'timings_ms':{}})
        class Request:
            async def is_disconnected(self):return False
        async def run():
            runner=Runner({});runner.ready=True;runner.process=SimpleNamespace(is_alive=lambda:True);runner.pipe=Pipe()
            await runner.search(b'SYNTHETIC','A',Request())
            await runner.search(b'SYNTHETIC','',Request(),namespace='operkontur',operation_kind='check')
        asyncio.run(run());self.assertEqual(sent[0][3],'search');self.assertEqual(sent[1][2:],('operkontur','check',None))

    def test_atomic_metadata_retries_transient_windows_reader_lock(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.json';atomic_json(path,{'revision':1})
            real_replace=os.replace;attempts=[]
            def replace(source,target):
                attempts.append(1)
                if len(attempts)==1:
                    error=PermissionError('SYNTHETIC sharing violation');error.winerror=32;raise error
                real_replace(source,target)
            with patch('services.visual_search.index2.os.replace',replace):atomic_json(path,{'revision':2})
            self.assertEqual(json.loads(path.read_text())['revision'],2);self.assertEqual(len(attempts),2)
    def test_views_bounded_overlap_and_explicit_cylinder(self):
        image=Image.new('RGB',(600,200),'white')
        views=list(representations(image,{'layout':'cylinder','full_wrap':True}))
        self.assertEqual(len(views),9)
        self.assertGreater(views[1][0]['region'][2],views[2][0]['region'][0])
        self.assertEqual(len(list(representations(image,{'layout':'auto'}))),1)
        self.assertEqual(len(list(representations(image,{'layout':'left_right'}))),3)
        with self.assertRaises(ValueError):profile({'regions':[[0,0,2,1]]})

    def test_safe_root_and_exact_pixels(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);im=Image.new('RGB',(80,50),'red');im.save(root/'a.png');im.save(root/'b.png',compress_level=0)
            a=read_source(root/'a.png');b=read_source(root/'b.png')
            self.assertNotEqual(a[1],b[1]);self.assertEqual(a[2],b[2])
            for relative in ('../a.png','/a.png','a/../../a.png','C:/a.png','a\\b.png'):
                with self.assertRaises((ValueError,OSError)):safe_source({'r':folder},'r',relative)

    def test_atomic_candidate_dedup_kit_scope_incremental_rollback(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);im=Image.new('RGB',(160,80),'red');ImageDraw.Draw(im).rectangle((70,5,100,70),fill='blue');im.save(root/'one.jpg')
            asset={'root':'r','relative':'one.jpg','id':'asset-a'}
            rows=[{'code':'00001','name':'Component','product_type':'A','kind_key':'stable-kind','assets':[asset], 'standalone':True,'namespace':'portal'},
                  {'code':'00002','name':'Kit1','product_type':'K','assets':[asset],'is_kit':True,'components':['00001'],'namespace':'portal'},
                  {'code':'00003','name':'Kit2','product_type':'K','assets':[asset],'is_kit':True,'components':['00001'],'namespace':'portal'},
                  {'code':'00004','name':'Private','product_type':'A','assets':[asset],'namespace':'operkontur'}]
            embed=FakeEmbedder();index=root/'index'
            first=build(rows,{'r':folder},index,'unused',{'stable-kind':{'layout':'left_right'}},embedder=embed)
            self.assertFalse((index/'current.json').exists())
            activate(index,first['pointer'],'unused',embedder=embed);engine=Engine(resolve_index(index),'unused',embedder=embed)
            result=engine.search((root/'one.jpg').read_bytes(),'A')
            self.assertEqual({x['code'] for x in result['items']},{'00001','00002','00003'})
            self.assertEqual(len(result['items']),3)
            self.assertEqual(next(x for x in result['items'] if x['code']=='00002')['relation'],'confirmed_component')
            private=engine.search((root/'one.jpg').read_bytes(),'A',namespace='operkontur')
            self.assertEqual({x['code'] for x in private['items']},{'00004'})
            public_again=engine.search((root/'one.jpg').read_bytes(),'A')
            self.assertEqual({x['code'] for x in public_again['items']},{'00001','00002','00003'})
            kits_only=engine.search((root/'one.jpg').read_bytes(),'K')
            self.assertEqual({x['code'] for x in kits_only['items']},{'00002','00003'})
            cache={p.name:p.stat().st_mtime_ns for p in index.glob('cache-*/*.npz')}
            second=build(rows,{'r':folder},index,'unused',{'stable-kind':{'layout':'left_right'}},embedder=embed)
            self.assertEqual(cache,{p.name:p.stat().st_mtime_ns for p in index.glob('cache-*/*.npz')})
            activate(index,second['pointer'],'unused',embedder=embed)
            self.assertEqual(json.loads((index/'previous.json').read_text()),first['pointer'])
            with self.assertRaises(ValueError):build(rows,{'r':folder},index,'unused',cancelled=lambda:True,embedder=embed)
            self.assertEqual(resolve_index(index).name,second['pointer']['generation'])
            engine.close()

    def test_durable_bounded_queue_cancel_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            m=Jobs({'jobs':folder});a=m.create('index',{'rows':[]});b=m.create('index',{'rows':[]});self.assertEqual(a['id'],b['id'])
            self.assertEqual(m.cancel(a['id'])['status'],'cancelled')
            self.assertEqual(m.resume(a['id'])['status'],'queued')
            self.assertNotIn('payload',m.public(m.get(a['id'])))

    def test_search_key_cannot_manage_and_management_requires_trusted_peer(self):
        with tempfile.TemporaryDirectory() as folder:
            app=FastAPI();search_key=bytes(range(32));management_key=bytes(reversed(range(32)))
            config={'jobs':folder,'key_hex':search_key.hex(),'management_key_hex':management_key.hex(),'management_clients':['testclient'],'source_roots':{}}
            install(app,config,SimpleNamespace())
            client=TestClient(app);path='/v2/manage/jobs/index';body=b'{"rows":[]}'
            self.assertEqual(client.post(path,content=body,headers=signed(search_key,'POST',path,'1',body)).status_code,401)
            result=client.post(path,content=body,headers=signed(management_key,'POST',path,'1',body))
            self.assertEqual(result.status_code,200);self.assertNotIn('catalogue_ref',result.json())
            self.assertEqual(len(list((Path(folder)/'catalogues').glob('*.json'))),1)
            administrator='12345678-1234-1234-1234-123456789abc'
            self.assertEqual(client.post(path,content=body,headers=signed(management_key,'POST',path,administrator,body)).status_code,200)
            from services.visual_search.protocol import Authentication
            from fastapi import HTTPException
            request=SimpleNamespace(headers={k.lower():v for k,v in signed(search_key,'POST',path,administrator,body).items()},url=SimpleNamespace(path=path,query=''))
            with self.assertRaises(HTTPException):Authentication(search_key).check(request,body)

    def test_designer_compares_within_batch_and_reports_partial_without_indexing(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);images=root/'images';images.mkdir();jobs=root/'jobs'
            image=Image.new('RGB',(80,50),'red');image.save(images/'a.png');image.save(images/'b.png',compress_level=0);(images/'bad.jpg').write_bytes(b'broken SYNTHETIC')
            config={'jobs':str(jobs),'source_roots':{'syn':str(images)},'index':str(root/'untouched-index'),'model':'unused'}
            manager=Jobs(config);job=manager.create('batch',{'files':[{'root':'syn','relative':n} for n in ('a.png','b.png','bad.jpg')]})
            class SyntheticEngine:
                rows=[];index_id='SYNTHETIC';embed=FakeEmbedder()
                def __init__(self,*a):pass
                def search(self,*a,**k):return {'items':[],'total':0,'status':'none','index_version':self.index_id}
            with patch('services.visual_search.resources.restrict_compute',lambda **k:None),patch('services.visual_search.engine.Engine',SyntheticEngine),patch('services.visual_search.engine.resolve_index',lambda p:p):execute(config,job['id'])
            result=manager.get(job['id']);self.assertEqual(result['status'],'partial');self.assertEqual(result['results'][1]['match_type'],'exact_pixels');self.assertTrue(result['results'][1]['within_batch_reference']);self.assertEqual(result['results'][2]['status'],'unreadable');self.assertFalse((root/'untouched-index').exists())

if __name__=='__main__':unittest.main()
