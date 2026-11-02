"""Management key is separate from legacy search; no path-bearing public endpoints."""
import asyncio, json, re, time
from pathlib import Path
from fastapi import Request, HTTPException
from .protocol import Authentication


def install(app,config,runner):
    if not config.get('management_key_hex'):return
    from .jobs2 import Jobs
    from .index2 import activate
    manager=Jobs(config);auth=Authentication(bytes.fromhex(config['management_key_hex']),allow_uuid=True)
    if config['management_key_hex']==config['key_hex']:raise ValueError('separate_management_key_required')
    async def body(request):
        if request.client.host not in config.get('management_clients',['127.0.0.1']):raise HTTPException(403,'management_peer')
        chunks=bytearray()
        async with asyncio.timeout(4):
            async for chunk in request.stream():
                if len(chunks)+len(chunk)>16*1024*1024:raise HTTPException(413,'management_size')
                chunks.extend(chunk)
        request.state.management_subject=auth.check(request,bytes(chunks))
        try:return json.loads(chunks) if chunks else {}
        except ValueError:raise HTTPException(422,'management_json') from None

    @app.get('/v2/manage/status')
    async def status(request:Request):
        await body(request)
        meta={}
        if runner.index:
            meta=json.loads((Path(config['index'])/runner.index/'manifest.json').read_text('utf-8'))
        return {'schema_version':2,'ready':runner.ready,'index_version':runner.index,'queue_active':runner.capacity.active,
                'counts':{k:meta.get(k) for k in ('products','unique_products','source_images','unique_images','kit_links')},'model_hash':meta.get('model_hash'),
                'namespaces':meta.get('namespaces',{}),'view_count':meta.get('view_count'),
                'model':{'name':'facebook/dinov2-small','revision':'ed25f3a31f01632728cabb09d1542f84ab7b0056','license':'Apache-2.0','source':'https://github.com/facebookresearch/dinov2','update_policy':'separate_verified_release'},
                'views_version':meta.get('views_version'),'created_epoch':meta.get('created_epoch'),'skipped':meta.get('skipped',[])[:100],
                'jobs':[manager.public(x) for x in await asyncio.to_thread(manager.all)]}

    @app.post('/v2/manage/check')
    async def check(request:Request):
        import base64
        value=await body(request)
        try:
            session=value.get('batch_session')
            if session is not None and not re.fullmatch('[a-f0-9]{32}',session):raise ValueError('session')
            context=(request.state.management_subject,session) if session else None
            raw=base64.b64decode(value['content'],validate=True)
            if len(raw)>2*1024*1024:raise ValueError('size')
            runner.capacity.enter()
            try:return await runner.search(raw,value.get('product_type',''),request,namespace='operkontur',operation_kind='check',check_context=context)
            finally:runner.capacity.leave();raw=None
        except (ValueError,KeyError):raise HTTPException(422,'invalid_image') from None

    @app.post('/v2/manage/check-session/close')
    async def close_check(request:Request):
        value=await body(request);session=value.get('batch_session','')
        if not re.fullmatch('[a-f0-9]{32}',session):raise HTTPException(422,'invalid_session')
        runner.capacity.enter()
        try:return await runner.search(b'','',request,namespace='operkontur',operation_kind='close-check',check_context=(request.state.management_subject,session))
        finally:runner.capacity.leave()

    @app.post('/v2/manage/jobs/{kind}')
    async def create(kind:str,request:Request):
        value=await body(request)
        try:return await asyncio.to_thread(manager.create,kind,value)
        except (ValueError,KeyError):raise HTTPException(422,'invalid_job') from None

    @app.post('/v2/manage/job/{identifier}/{action}')
    async def action(identifier:str,action:str,request:Request):
        value=await body(request)
        try:
            if action=='cancel':return await asyncio.to_thread(manager.cancel,identifier)
            if action=='resume':return await asyncio.to_thread(manager.resume,identifier)
            if action=='decision':
                job=await asyncio.to_thread(manager.get,identifier)
                if value.get('decision') not in ('new_variant','use_existing','needs_review'):raise ValueError('decision')
                found=False
                for row in job.get('results',[]):
                    if row['id']==value.get('file_id'):
                        job.setdefault('decision_history',[]).append({'file_id':row['id'],'before':row.get('decision'),'after':value['decision'],'actor':request.state.management_subject,'at':time.time()})
                        row['decision']=value['decision'];found=True
                if not found:raise ValueError('file_id')
                from .index2 import atomic_json
                atomic_json(manager.root/(identifier+'.json'),job);return manager.public(job)
            if action=='activate':
                job=await asyncio.to_thread(manager.get,identifier)
                if job['kind']!='index' or job['status']!='complete':raise ValueError('candidate_incomplete')
                await asyncio.to_thread(activate,config['index'],job['candidate']['pointer'],config['model'])
                return {'status':'activating','pointer':job['candidate']['pointer']}
            raise ValueError('action')
        except (ValueError,KeyError,OSError):raise HTTPException(422,'invalid_job_action') from None

    @app.post('/v2/manage/rollback')
    async def rollback(request:Request):
        await body(request)
        try:
            pointer=json.loads((Path(config['index'])/'previous.json').read_text('utf-8'))
            await asyncio.to_thread(activate,config['index'],pointer,config['model']);return {'status':'activating','pointer':pointer}
        except (OSError,ValueError):raise HTTPException(422,'rollback_unavailable') from None

    @app.get('/v2/manage/job/{identifier}')
    async def get(identifier:str,request:Request):
        await body(request)
        try:return manager.public(await asyncio.to_thread(manager.get,identifier))
        except (FileNotFoundError,ValueError):raise HTTPException(404,'job_not_found') from None
        except OSError:raise HTTPException(503,'job_storage_busy') from None
    app.state.visual_jobs=manager
    return manager
