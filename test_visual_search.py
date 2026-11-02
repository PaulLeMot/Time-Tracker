"""Isolated tests: no main/database imports, no production startup or network."""
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import httpx
import numpy as np
from PIL import Image
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from services.visual_search.engine import decode, geometry, Engine, resolve_index, build
from services.visual_search.gateway import create_gateway
from services.visual_search.protocol import Authentication, Capacity, signed, read_body, MAX_BODY
from services.visual_search.worker import create_worker


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.key = bytes(range(32))

    def test_proof_binds_query_subject_body_and_rejects_replay(self):
        app = FastAPI(); auth = Authentication(self.key)
        @app.post('/v1/search')
        async def endpoint(request: Request):
            return {'subject': auth.check(request, await read_body(request))}
        with TestClient(app) as client:
            path='/v1/search?product_type=A'
            headers=signed(self.key,'POST',path,'123',b'abc')
            self.assertEqual(client.post(path,content=b'bad',headers=headers).status_code,401)
            self.assertEqual(client.post(path,content=b'abc',headers=headers).status_code,200)
            self.assertEqual(client.post(path,content=b'abc',headers=headers).status_code,401)
            headers=signed(self.key,'POST',path,'123',b'abc')
            self.assertEqual(client.post('/v1/search?product_type=B',content=b'abc',headers=headers).status_code,401)

    def test_body_limit_even_without_content_length_and_capacity(self):
        app=FastAPI()
        @app.post('/')
        async def endpoint(request: Request):
            return {'bytes':len(await read_body(request))}
        with TestClient(app) as client:
            self.assertEqual(client.post('/',content=b'x'*(MAX_BODY+1)).status_code,413)
            self.assertEqual(client.post('/',content=iter([b'x'*MAX_BODY,b'y'])).status_code,413)
        capacity=Capacity(1);capacity.enter()
        with self.assertRaises(Exception):capacity.enter()
        capacity.leave();self.assertEqual(capacity.active,0)

    def test_decode_rejects_broken_tiny_and_bomb_and_applies_exif(self):
        for body in (b'',b'not_an_image',b'x'*(MAX_BODY+1)):
            with self.assertRaises(ValueError):decode(body)
        image=Image.new('RGB',(60,40),'red');exif=Image.Exif();exif[274]=6
        buf=io.BytesIO();image.save(buf,'JPEG',exif=exif)
        self.assertEqual(decode(buf.getvalue()).size,(40,60))
        buf=io.BytesIO();Image.new('RGB',(4000,4000)).save(buf,'PNG')
        with self.assertRaises(ValueError):decode(buf.getvalue())

    def test_no_geometry_with_uniform_image(self):
        self.assertEqual(geometry(np.zeros((0,2),'float32'),np.zeros((0,128),'uint8'),np.zeros((0,2),'float32'),np.zeros((0,128),'uint8')),(0,0.0))

    def gateway(self, active=True, worker_status=200):
        async def profile(request):
            if request.headers.get('cookie')!='session=test':return httpx.Response(401)
            return httpx.Response(200,json={'id':12,'is_active':active})
        async def worker(request):
            self.assertNotIn('cookie',request.headers)
            self.assertNotIn('authorization',request.headers)
            self.assertTrue(request.headers.get('x-vs-proof'))
            return httpx.Response(worker_status,json={'api_version':1,'product_types':['A']})
        config={'origin':'https://portal.test','worker_url':'https://worker.test','key_hex':self.key.hex(),'enabled':True}
        return create_gateway(config,auth_transport=httpx.MockTransport(profile),worker_transport=httpx.MockTransport(worker))

    def test_gateway_requires_active_session_origin_exact_type_and_content_type(self):
        with TestClient(self.gateway()) as client:
            path='/api/visual-search/search?product_type=A'
            self.assertEqual(client.post(path,content=b'x').status_code,403)
            self.assertEqual(client.post(path,headers={'Origin':'https://portal.test'},content=b'x').status_code,401)
            h={'Origin':'https://portal.test','Cookie':'session=test','Content-Type':'image/jpeg'}
            self.assertEqual(client.post(path,headers=h,content=b'x').status_code,200)
            self.assertEqual(client.post('/api/visual-search/search?product_type=',headers=h,content=b'x').status_code,200)
            self.assertEqual(client.post(path,headers=h|{'Origin':'https://foreign.test'},content=b'x').status_code,403)
            self.assertEqual(client.post(path,headers=h|{'Content-Type':'multipart/form-data'},content=b'x').status_code,415)
            self.assertEqual(client.post(path,headers=h,content=b'x'*(MAX_BODY+1)).status_code,413)
        with TestClient(self.gateway(active=False)) as client:
            self.assertEqual(client.get('/api/visual-search/capabilities',headers={'Cookie':'session=test'}).status_code,403)

    def test_no_insecure_nonloopback_worker_or_profile_ssrf(self):
        config={'origin':'https://portal.test','worker_url':'http://192.0.2.1','key_hex':self.key.hex()}
        with self.assertRaises(ValueError):create_gateway(config)
        config['worker_url']='https://worker.test';config['profile_url']='http://192.0.2.2/api/auth/profile'
        with self.assertRaises(ValueError):create_gateway(config)

    def test_remote_worker_checks_socket_peer_before_body_or_hmac(self):
        config={'bind':'192.0.2.1','key_hex':self.key.hex()}
        with self.assertRaises(ValueError):create_worker(config)
        app=create_worker(config|{'allowed_clients':['192.0.2.2']})
        # No lifespan/compute is needed: the network guard rejects before reading.
        client=TestClient(app, client=('192.0.2.3',32100))
        response=client.post('/v1/search?product_type=A',content=b'not-read',
                             headers={'x-forwarded-for':'192.0.2.2'})
        self.assertEqual(response.status_code,403)
        self.assertEqual(response.json()['detail'],'client_not_allowed')
        client=TestClient(app, client=('192.0.2.2',32100))
        self.assertEqual(client.get('/health').status_code,503)

    def test_worker_outage_is_bounded_and_no_store(self):
        with TestClient(self.gateway(worker_status=503)) as client:
            response=client.get('/api/visual-search/capabilities',headers={'Cookie':'session=test'})
            self.assertEqual(response.status_code,503)
            self.assertEqual(response.headers['cache-control'],'no-store')


@unittest.skipUnless(os.getenv('VS_SYNTHETIC_ROOT') and os.getenv('VS_MODEL_ROOT'),'explicit synthetic/model paths required')
class IndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(os.environ['VS_SYNTHETIC_ROOT']);cls.model=Path(os.environ['VS_MODEL_ROOT'])
        assert (cls.root/'DATA_CLASS.txt').read_text().strip()=='SYNTHETIC'
        cls.engine=Engine(resolve_index(cls.root/'index'),cls.model)

    def test_category_before_topk_and_all_duplicate_codes(self):
        body=(self.root/'images/97000.jpg').read_bytes()
        result=self.engine.search(body,'Тестовый вид А')
        self.assertGreaterEqual(result['total'],55)
        self.assertEqual(len({x['code'] for x in result['items']}),result['total'])
        self.assertTrue(all(x['product_type']=='Тестовый вид А' for x in result['items']))
        result=self.engine.search(body,'Тестовый вид Б')
        self.assertEqual([x['code'] for x in result['items']],['98054'])
        self.assertIn('98054',{x['code'] for x in self.engine.search(body,'')['items']})

    @classmethod
    def tearDownClass(cls):
        cls.engine.close()

    def test_corrupt_index_and_pointer_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'index';shutil.copytree(self.root/'index',target)
            pointer=json.loads((target/'current.json').read_text())
            (target/pointer['generation']/'vectors.npy').write_bytes(b'corrupt')
            with self.assertRaises(ValueError):Engine(resolve_index(target),self.model)
            pointer['generation']='../elsewhere';(target/'current.json').write_text(json.dumps(pointer))
            with self.assertRaises(ValueError):resolve_index(target)

    def test_incremental_rebuild_deletion_atomic_pointer_and_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);shutil.copytree(self.root/'images',root/'images')
            catalogue=root/'catalogue.json';shutil.copyfile(self.root/'catalogue.json',catalogue)
            build(catalogue,root/'images',root/'index',self.model)
            previous=(root/'index/current.json').read_bytes()
            cache=list((root/'index').glob('cache-*/*.npz'));mtimes={p.name:p.stat().st_mtime_ns for p in cache}
            (root/'images/97011.jpg').unlink()
            manifest=build(catalogue,root/'images',root/'index',self.model)
            self.assertEqual(manifest['skipped'][0]['code'],'97011')
            self.assertEqual(mtimes,{p.name:p.stat().st_mtime_ns for p in cache})
            self.assertNotIn('97011',{r['code'] for r in Engine(resolve_index(root/'index'),self.model).rows})
            (root/'index/current.json').write_bytes(previous)
            self.assertIn('97011',{r['code'] for r in Engine(resolve_index(root/'index'),self.model).rows})


if __name__=='__main__':unittest.main()
