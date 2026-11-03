"""No production DB/network. Protocol, privacy, fail-open search and evidence gates."""
import asyncio,copy,hashlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from PIL import Image
from fastapi import HTTPException
from fastapi.testclient import TestClient
from services.visual_search.enhance import merge,needs_fallback,Enhancer
from services.visual_search.protocol import signed
from services.visual_search.worker import Runner,create_worker
from services.visual_search.gateway import create_gateway
import httpx


def item(code,score,status='uncertain'):
    return {'code':code,'name':'SYNTHETIC','product_type':'A','score':score,'similarity_status':status,'evidence':'geometry' if status=='confirmed' else 'weak','relation':'direct'}


def result(items):
    return {'items':items,'total':len(items),'index_version':'index-123','timings_ms':{},'ranking_version':'synthetic','status':'weak'}


class EnhancerTests(unittest.TestCase):
    def test_correlated_scores_do_not_confirm_or_sum(self):
        original=result([item('00001',.78)]);variant=result([item('00002',.99,'confirmed'),item('00001',.95,'confirmed')])
        merged=merge(original,[('processed',variant)])
        self.assertEqual(len(merged['items']),2);self.assertEqual(merged['items'][0]['score'],.945)
        self.assertTrue(all(r['similarity_status']!='confirmed' and r['evidence']=='weak' for r in merged['items']))
        self.assertEqual(original['items'][0]['score'],.78)

    def test_original_confirmed_item_is_protected(self):
        original=result([item('00001',.93,'confirmed')])
        merged=merge(original,[('processed',result([item('00002',.999,'confirmed')]))])
        self.assertEqual(merged['items'][0]['code'],'00001');self.assertEqual(merged['items'][0]['query_branch'],'original')
        self.assertEqual(merged['items'][0]['similarity_status'],'confirmed');self.assertFalse(needs_fallback(original))
        self.assertTrue(needs_fallback(result([])))

    def test_no_artificial_score_increase_from_duplicate_branches(self):
        original=result([item('00001',.8)]);variant=result([item('00001',.82)])
        merged=merge(original,[('object',variant),('processed',variant)])
        self.assertEqual(merged['items'][0]['score'],.8);self.assertEqual(merged['total'],1)

    def test_original_geometry_anchors_top_without_calling_it_confirmed(self):
        row=item('00001',.81);row.update(geometry_inliers=18,geometry_support=.6)
        merged=merge(result([row]),[('processed',result([item('00002',.99,'confirmed')]))])
        self.assertEqual(merged['items'][0]['code'],'00001');self.assertEqual(merged['items'][0]['similarity_status'],'uncertain');self.assertEqual(merged['status'],'weak')

    def test_weights_fail_closed_before_loading_model(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root,'u2netp.onnx').write_bytes(b'SYNTHETIC corrupt model')
            with self.assertRaisesRegex(ValueError,'checksum'):Enhancer(root)

    def test_plane_does_not_transform_blank_frame(self):
        image=Image.new('RGB',(300,300),'white');out,reason=Enhancer.plane(image)
        self.assertIs(out,image);self.assertEqual(reason,'plane_not_detected')

    def test_authenticated_gateway_routes_manual_and_strategy_without_credentials(self):
        forwarded=[]
        async def profile(request):return httpx.Response(200,json={'id':12,'is_active':True})
        async def worker(request):
            forwarded.append(str(request.url));self.assertNotIn('cookie',request.headers)
            self.assertTrue(request.headers.get('x-vs-proof'));return httpx.Response(200,json={'ok':True})
        app=create_gateway({'origin':'https://portal.test','worker_url':'https://worker.test','key_hex':bytes(range(32)).hex(),'enabled':True},auth_transport=httpx.MockTransport(profile),worker_transport=httpx.MockTransport(worker))
        with TestClient(app) as client:
            headers={'Origin':'https://portal.test','Cookie':'session=SYNTHETIC','Content-Type':'image/jpeg'}
            self.assertEqual(client.post('/api/visual-search/enhance',headers=headers,content=b'SYNTHETIC').status_code,200)
            self.assertEqual(client.post('/api/visual-search/search?enhancement=off',headers=headers,content=b'SYNTHETIC').status_code,200)
            self.assertEqual(client.post('/api/visual-search/enhance',headers=headers|{'Origin':'https://foreign.test'},content=b'SYNTHETIC').status_code,403)
            self.assertEqual(client.post('/api/visual-search/search?enhancement=arbitrary',headers=headers,content=b'SYNTHETIC').status_code,422)
        self.assertTrue(forwarded[0].endswith('/v1/enhance?product_type='));self.assertTrue(forwarded[1].endswith('enhancement=off'))

    def worker_case(self, strategy='auto', confirmed=False, failure=False, preview=False, enabled=True, busy=False):
        calls=[];key=bytes(range(32));original=result([item('00001',.94 if confirmed else .78,'confirmed' if confirmed else 'uncertain')])
        async def start(runner):
            runner.ready=True;runner.types=['A'];runner.index='index-123';runner.process=SimpleNamespace(is_alive=lambda:True)
        def stop(runner):runner.ready=False;runner.process=None
        async def search(runner,body,kind,request,namespace='portal',operation_kind='search',check_context=None):
            calls.append(operation_kind)
            if operation_kind=='search':
                if busy:runner.capacity.active+=1
                return copy.deepcopy(original)
            if failure:raise HTTPException(503,'SYNTHETIC failed enhancement')
            if operation_kind=='enhance':return {'content_type':'image/jpeg','image_base64':'SYNTHETIC','timings_ms':{}}
            self.assertEqual(check_context['index_version'],'index-123')
            return {'variants':[('processed',result([item('00002',.99,'confirmed')]))],'enhancement':{'operations':['object_mask']},'timings_ms':{}}
        with tempfile.TemporaryDirectory() as root:
            Path(root,'current.json').write_text('{}')
            config={'key_hex':key.hex(),'index':root,'model':'unused','enhancer_model':root if enabled else None,'enhancer_auto':True}
            with patch.object(Runner,'start',start),patch.object(Runner,'stop',stop),patch.object(Runner,'search',search):
                with TestClient(create_worker(config)) as client:
                    path=('/v1/enhance' if preview else '/v1/search')+'?product_type=A&enhancement='+strategy;body=b'SYNTHETIC'
                    response=client.post(path,headers=signed(key,'POST',path,'12',body)|{'Content-Type':'image/jpeg'},content=body)
        return response,calls

    def test_weak_original_uses_two_stage_pipeline_without_new_confirmation(self):
        response,calls=self.worker_case();self.assertEqual(response.status_code,200);self.assertEqual(calls,['search','enhance-search'])
        data=response.json();self.assertEqual(data['items'][0]['code'],'00002');self.assertEqual(data['items'][0]['similarity_status'],'uncertain');self.assertEqual(data['total'],2)

    def test_strong_original_skips_processing(self):
        response,calls=self.worker_case(confirmed=True);self.assertEqual(calls,['search']);self.assertEqual(response.json()['items'][0]['code'],'00001')

    def test_failure_keeps_original_metadata(self):
        response,calls=self.worker_case(failure=True);self.assertEqual(response.status_code,200);self.assertEqual(response.json()['items'][0]['code'],'00001')
        self.assertEqual(response.json()['enhancement']['status'],'unavailable_original_used')

    def test_opt_out_skips_processing(self):
        response,calls=self.worker_case(strategy='off');self.assertEqual(calls,['search']);self.assertEqual(response.status_code,200)

    def test_busy_does_not_start_extra_work(self):
        response,calls=self.worker_case(busy=True);self.assertEqual(calls,['search']);self.assertEqual(response.json()['enhancement']['status'],'busy_original_used')

    def test_preview_has_no_results_cursor_and_disabled_rejects(self):
        response,calls=self.worker_case(preview=True);self.assertEqual(calls,['enhance']);self.assertNotIn('cursor',response.json())
        response,calls=self.worker_case(preview=True,enabled=False);self.assertEqual(response.status_code,503);self.assertEqual(calls,[])

if __name__=='__main__':unittest.main()
