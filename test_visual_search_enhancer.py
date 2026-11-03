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
        row=item('00001',.81);row.update(geometry_inliers=18,geometry_support=.6,geometry_reciprocal=True)
        merged=merge(result([row]),[('processed',result([item('00002',.99,'confirmed')]))])
        self.assertEqual(merged['items'][0]['code'],'00001');self.assertEqual(merged['items'][0]['similarity_status'],'uncertain');self.assertEqual(merged['status'],'weak')

    def test_weights_fail_closed_before_loading_model(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root,'u2netp.onnx').write_bytes(b'SYNTHETIC corrupt model')
            with self.assertRaisesRegex(ValueError,'checksum'):Enhancer(root)

    def test_unchanged_dense_frame_preserves_product_for_ambiguous_shared_print(self):
        original=result([item('00001',.79),item('00002',.73)])
        supported=item('00001',.85);supported.update(geometry_reciprocal=True,geometry_inliers=40,geometry_support=.75)
        details=result([item('00002',.87),supported])
        variants=[('original_details',details),('object',result([item('00002',.98)]))]
        merged=merge(original,variants)
        self.assertEqual(merged['items'][0]['code'],'00001')
        self.assertNotEqual(merged['items'][0]['similarity_status'],'confirmed')
        # Clearly stronger original-frame evidence for another print can win.
        details['items'][0]['score']=.97
        self.assertEqual(merge(original,variants)['items'][0]['code'],'00002')

    def test_new_partial_profiles_and_rescue_never_create_green(self):
        import numpy as np
        from services.visual_search.retrieval2 import search
        buffer=io.BytesIO();Image.new('RGB',(80,80),'white').save(buffer,'JPEG')
        row={'code':'00001','name':'SYN','product_type':'A','feature':0,'namespace':'portal','profile':{'revision':2},'view':{'role':'fragment'}}
        engine=SimpleNamespace(rows=[row],vectors=np.array([[.99,.01]],dtype='float32'),points=np.zeros((1,2),'float32'),descriptors=np.zeros((1,128),'uint8'),offsets=np.array([0,1]),embed=lambda image:np.array([1,0],dtype='float32'),index_id='index-SYN')
        with patch('services.visual_search.engine.geometry',lambda *a,**kw:(20,.8)):
            out=search(engine,buffer.getvalue());self.assertEqual(out['items'][0]['similarity_status'],'uncertain')
            row['profile']['revision']=1;self.assertEqual(search(engine,buffer.getvalue())['items'][0]['similarity_status'],'confirmed')
            engine.vectors[0,0]=.4;self.assertEqual(search(engine,buffer.getvalue())['total'],0)
            out=search(engine,buffer.getvalue(),mode='rescue');self.assertEqual(out['total'],1);self.assertNotEqual(out['items'][0]['similarity_status'],'confirmed')
        with patch('services.visual_search.engine.geometry',lambda *a,**kw:(4,.1)):
            self.assertEqual(search(engine,buffer.getvalue(),mode='rescue')['total'],0)

    def test_product_layouts_remain_bounded_and_preserve_whole(self):
        from services.visual_search.product_profiles import preset
        from services.visual_search.views import representations
        image=Image.new('RGB',(500,500),'white')
        for label in ('Пенал','Минидак','Кружка','Обложка на паспорт','Набор значков (6шт)','Брелок Набор 2+1'):
            settings=preset(label);views=list(representations(image,settings))
            self.assertLessEqual(len(views),9);self.assertEqual(settings['revision'],2)
            self.assertEqual(views[0][0]['role'],'whole');self.assertEqual(views[0][1].tobytes(),image.tobytes())
        self.assertIsNone(preset('UNKNOWN_KIND'))

    def test_reciprocal_geometry_rejects_repeated_many_to_one_votes(self):
        import numpy as np
        from services.visual_search.engine import geometry
        rng=np.random.default_rng(9128)
        reference=rng.uniform(0,255,(30,128)).astype('float32')
        # Many distinct camera positions describing the same tiny printed mark.
        query=np.tile(reference[0],(80,1))+rng.normal(0,.01,(80,128)).astype('float32')
        points=rng.uniform(0,500,(30,2)).astype('float32')
        qp=rng.uniform(0,960,(80,2)).astype('float32')
        self.assertEqual(geometry(qp,query,points,reference,strict=True),(0,0.0))
        # Distinct real correspondences survive translation and scale.
        qp=points*1.4+20
        count,support=geometry(qp,reference,points,reference,strict=True)
        self.assertGreaterEqual(count,25);self.assertGreater(support,.8)

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
