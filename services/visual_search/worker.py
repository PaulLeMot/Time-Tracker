"""One warmed compute subprocess; bounded admission and hard execution deadline."""
import asyncio
import ipaddress
from contextlib import asynccontextmanager
import multiprocessing as mp
import os
from pathlib import Path
import secrets
import sys
import time
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from .protocol import Authentication, Capacity, read_body


def compute(connection, index, model, resources, enhancer_root=None):
    # Prevent diagnostic core dumps on platforms that support resource limits.
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except ImportError:
        pass
    try:
        from .resources import restrict_compute
        job_handle = restrict_compute(**resources)
        from .engine import Engine, resolve_index
        engine = Engine(resolve_index(index), model)
        enhancer = None
        check_sessions = {}
        public_types=sorted({r['product_type'] for r in engine.rows if r.get('namespace','portal')=='portal'})
        public_codes={r['code'] for r in engine.rows if r.get('namespace','portal')=='portal'}
        connection.send(('ready', public_types, engine.index_id, public_codes))
        while True:
            message = connection.recv()
            body, kind = message[:2]
            namespace = message[2] if len(message)>2 else 'portal'
            try:
                context=message[4] if len(message)>4 else None
                if len(message)>3 and message[3]=='close-check':
                    check_sessions.pop(context,None);connection.send(('ok',{'closed':True,'timings_ms':{}}));continue
                operation_kind = message[3] if len(message)>3 else 'search'
                if operation_kind in ('enhance', 'enhance-search'):
                    if not enhancer_root: raise ValueError('enhancer_disabled')
                    if enhancer is None:
                        from .enhance import Enhancer
                        enhancer = Enhancer(enhancer_root)
                    result = enhancer.preview(body,engine,kind) if operation_kind == 'enhance' else enhancer.search(engine,body,kind,namespace,baseline=context)
                    result['timings_ms'] = {'compute': result.get('elapsed_ms',result.get('enhancement',{}).get('elapsed_ms',0))}
                else:
                    result = engine.search(body, kind, namespace=namespace)
                if len(message)>3 and message[3]=='check':
                    import hashlib,io
                    from PIL import Image,ImageOps
                    with Image.open(io.BytesIO(body)) as raw:
                        normalized=ImageOps.exif_transpose(raw).convert('RGB')
                    pixel_hash=hashlib.sha256(f'RGB:{normalized.width}:{normalized.height}:'.encode()+normalized.tobytes()).hexdigest()
                    byte_hash=hashlib.sha256(body).hexdigest()
                    exact=[{'code':r['code'],'asset_id':r.get('asset_id')} for r in engine.rows if r.get('namespace','portal')==namespace and (r.get('sha256')==byte_hash or r.get('pixel_sha256')==pixel_hash)]
                    result.update(sha256=byte_hash,pixel_sha256=pixel_hash,match_type='exact_file' if any(r.get('sha256')==byte_hash and r.get('namespace','portal')==namespace for r in engine.rows) else 'exact_pixels' if exact else 'visual' if result['items'] else 'none',exact_matches=list({r['code']:r for r in exact}.values()))
                    if context:
                        from .engine import local_features,geometry
                        import numpy as np
                        now=time.monotonic()
                        check_sessions={k:v for k,v in check_sessions.items() if now-v['updated']<90}
                        if context not in check_sessions:
                            if len(check_sessions)>=4:check_sessions.pop(next(iter(check_sessions)))
                            check_sessions[context]={'updated':now,'items':[]}
                        session=check_sessions[context];session['updated']=now
                        if len(session['items'])>=64:raise ValueError('upload_batch_limit')
                        normalized.thumbnail((1024,1024));vector=engine.embed(normalized);points,desc=local_features(normalized);matches=[]
                        for ordinal,prior in enumerate(session['items']):
                            score=float(vector@prior['vector'])
                            exact_kind='exact_file' if prior['sha']==byte_hash else 'exact_pixels' if prior['pixels']==pixel_hash else None
                            if not exact_kind and score<.75:continue
                            inliers,geo=geometry(points,desc,prior['points'],prior['descriptors'])
                            matches.append({'ordinal':ordinal,'type':exact_kind or 'visual','score':round(score,5),'status':'confirmed' if exact_kind or score>=.92 and inliers>=10 and geo>=.30 else 'uncertain'})
                        result['within_batch']=sorted(matches,key=lambda x:-x['score'])[:5]
                        session['items'].append({'sha':byte_hash,'pixels':pixel_hash,'vector':vector,'points':points,'descriptors':desc})
                connection.send(('ok', result))
            except ValueError:
                connection.send(('error', 'invalid_image_or_type'))
            finally:
                body = None
                message = result = None
    except (EOFError, BrokenPipeError):
        pass
    except Exception as error:
        # Never emit exception dumps containing a frame/request.
        try:
            import traceback
            frames = [(Path(f.filename).name, f.name, f.lineno) for f in traceback.extract_tb(error.__traceback__)[-4:]]
            connection.send(('fatal', type(error).__name__, frames))
        except (OSError, EOFError):
            pass
    finally:
        connection.close()


class Runner:
    def __init__(self, config):
        self.config, self.process, self.pipe = config, None, None
        maximum=config.get('queue_capacity',3)
        if type(maximum) is not int or not 1<=maximum<=8:raise ValueError('queue_capacity')
        self.lock, self.capacity = asyncio.Lock(), Capacity(maximum)
        self.ready, self.types, self.index = False, [], None
        self.codes = set()
        self.error = None
        self.start_lock = asyncio.Lock()

    def stop(self):
        self.ready = False
        if self.process is not None:
            self.process.terminate()
            self.process.join(timeout=2)
            self.process.close()
            self.process = None
        if self.pipe:
            self.pipe.close()
            self.pipe = None

    async def start(self):
        async with self.start_lock:
            await self._start()

    async def _start(self):
        self.stop()
        context = mp.get_context('spawn')
        if os.name == 'nt':
            # Use the real interpreter, not the venv launcher: termination must stop
            # the actual compute process rather than leave its child running.
            executable = Path(sys._base_executable).with_name('pythonw.exe')
            if not executable.is_file():
                raise ValueError('windowless_python_required')
            context.set_executable(str(executable))
        parent, child = context.Pipe()
        self.pipe = parent
        self.process = context.Process(target=compute, args=(child, self.config['index'], self.config['model'], self.config.get('resources', {}), self.config.get('enhancer_model')), daemon=True)
        self.process.start()
        process = self.process
        child.close()
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and self.process is process and process.is_alive():
            if parent.poll():
                message = parent.recv()
                if message[0] == 'ready':
                    self.ready, self.types, self.index = True, message[1], message[2]
                    self.codes = message[3] if len(message)>3 else set()
                    self.error = None
                    return
                self.error = message[1:] if len(message) > 1 else 'compute_init_failed'
                break
            await asyncio.sleep(.02)
        if self.process is process:
            self.stop()

    async def search(self, body, kind, request, namespace='portal', operation_kind='search', check_context=None):
        started = time.monotonic()
        async with asyncio.timeout(16 if operation_kind in ('enhance','enhance-search') else 18):
            async with self.lock:
                if not self.ready or self.process is None:
                    raise HTTPException(503, 'warming_or_unavailable')
                if not self.process.is_alive():
                    self.stop()
                    raise HTTPException(503, 'warming_or_unavailable')
                if await request.is_disconnected():
                    raise HTTPException(499, 'cancelled')
                queued = (time.monotonic() - started) * 1000
                async def exchange():
                    await asyncio.to_thread(self.pipe.send, (body, kind, namespace, operation_kind, check_context))
                    return await asyncio.to_thread(self.pipe.recv)
                operation = asyncio.create_task(exchange())
                try:
                    while not operation.done():
                        if not self.process.is_alive():
                            raise RuntimeError('compute_unavailable')
                        if await request.is_disconnected():
                            raise asyncio.CancelledError()
                        await asyncio.sleep(.01)
                    response = await operation
                except BaseException:
                    self.stop()  # Never leave timed-out/stale work consuming native CPU.
                    raise
                finally:
                    if not operation.done():
                        operation.cancel()
                    await asyncio.gather(operation, return_exceptions=True)
                if response[0] == 'error':
                    raise HTTPException(422, response[1])
                if response[0] != 'ok':
                    self.stop()
                    raise HTTPException(503, 'compute_unavailable')
                response[1]['timings_ms']['queue'] = queued
                return response[1]


def create_worker(config):
    # Use the socket peer, never forwarding headers. This also protects hosts
    # whose system firewall is managed separately or disabled.
    allowed_clients = {str(ipaddress.ip_address(x)) for x in config.get('allowed_clients', [])}
    if config.get('bind', '127.0.0.1') != '127.0.0.1' and not allowed_clients:
        raise ValueError('remote_worker_requires_client_allowlist')
    runner = Runner(config)
    auth = Authentication(bytes.fromhex(config['key_hex']))
    cache = {}
    recovery = None
    staged = None

    @asynccontextmanager
    async def lifespan(app):
        nonlocal recovery, staged
        await runner.start()
        pointer_file = Path(config['index']) / 'current.json'
        pointer_bytes = pointer_file.read_bytes()
        attempted_pointer = pointer_bytes

        async def stage_index(expected_pointer):
            nonlocal pointer_bytes, staged
            replacement = Runner(config)
            staged = replacement
            try:
                await replacement.start()
                if not replacement.ready or pointer_file.read_bytes() != expected_pointer:
                    return
                async with runner.lock:
                    if not runner.ready:
                        return
                    old_process, old_pipe = runner.process, runner.pipe
                    runner.process, runner.pipe = replacement.process, replacement.pipe
                    runner.types, runner.index = replacement.types, replacement.index
                    runner.codes = replacement.codes
                    replacement.process = replacement.pipe = None
                    pointer_bytes = expected_pointer
                    old_process.terminate(); old_process.join(timeout=2); old_process.close(); old_pipe.close()
            except (OSError, ValueError, EOFError):
                pass
            finally:
                replacement.stop()
                staged = None

        reload_task = None
        async def supervise():
            nonlocal recovery, reload_task, attempted_pointer
            while True:
                await asyncio.sleep(.5)
                if management is not None:
                    try:await asyncio.to_thread(management.tick)
                    except OSError:pass  # Transient storage contention must not stop query supervision.
                if runner.ready and (runner.process is None or not runner.process.is_alive()):
                    runner.stop()
                if not runner.ready and (recovery is None or recovery.done()):
                    recovery = asyncio.create_task(runner.start())
                if runner.ready and staged is None and (reload_task is None or reload_task.done()):
                    try:
                        value = pointer_file.read_bytes()
                        if value != pointer_bytes and value != attempted_pointer:
                            attempted_pointer = value
                            reload_task = asyncio.create_task(stage_index(value))
                    except OSError:
                        pass  # Keep the known good, warmed generation.
        supervisor = asyncio.create_task(supervise())
        yield
        supervisor.cancel()
        await asyncio.gather(supervisor, return_exceptions=True)
        if reload_task is not None:
            reload_task.cancel()
            await asyncio.gather(reload_task, return_exceptions=True)
        if staged is not None:
            staged.stop()
        if recovery is not None:
            recovery.cancel()
            await asyncio.gather(recovery, return_exceptions=True)
        runner.stop()
        cache.clear()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    from .management2 import install
    management = install(app, config, runner)

    @app.middleware('http')
    async def no_store(request, call_next):
        peer = request.client.host if request.client else ''
        if allowed_clients and peer not in allowed_clients:
            return JSONResponse({'detail': 'client_not_allowed'}, status_code=403,
                                headers={'Cache-Control': 'no-store'})
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/health')
    async def health():
        return JSONResponse({'ready': runner.ready, 'status': 'ready' if runner.ready else 'warming_or_unavailable'}, status_code=200 if runner.ready else 503)

    @app.get('/v1/capabilities')
    async def capabilities(request: Request):
        auth.check(request, b'')
        if not runner.ready:
            raise HTTPException(503, 'warming_or_unavailable')
        return {'api_version': 1, 'product_types': runner.types, 'index_version': runner.index, 'max_body': 2 * 1024 * 1024,
                'enhancement': {'version':'enhancer-1.1','available':bool(config.get('enhancer_model')),'automatic':config.get('enhancer_auto',False)}}

    @app.get('/v1/catalogue/{code}')
    async def catalogue_code(code: str, request: Request):
        auth.check(request, b'')
        if not runner.ready:raise HTTPException(503, 'warming_or_unavailable')
        if code not in runner.codes:raise HTTPException(404, 'catalogue_code_not_allowed')
        return {'code':code,'index_version':runner.index}

    @app.get('/v1/results')
    async def results(request: Request, cursor: str = Query(pattern='^[a-f0-9]{32}$'), offset: int = Query(0, ge=0, le=200000)):
        subject = auth.check(request, b'')
        entry = cache.get(cursor)
        if not entry or entry[0] < time.monotonic() or entry[1] != subject:
            raise HTTPException(410, 'results_expired')
        return page(entry[2], cursor, offset)

    def page(result, cursor, offset=0):
        return result | {'items': result['items'][offset:offset+30], 'cursor': cursor,
                         'next_offset': offset+30 if offset+30 < result['total'] else None}

    @app.post('/v1/enhance')
    @app.post('/v1/search')
    async def search(request: Request, product_type: str = Query('', max_length=2000), enhancement: str = Query('auto', pattern='^(auto|off|force)$')):
        nonlocal recovery
        request_started=time.monotonic()
        runner.capacity.enter()
        try:
            body = await read_body(request)
            subject = auth.check(request, body)
            active_subjects = getattr(app.state, 'active_subjects', set())
            app.state.active_subjects = active_subjects
            if subject in active_subjects:
                raise HTTPException(429, 'one_active_search_per_employee')
            if request.headers.get('content-type') not in ('image/jpeg', 'image/png', 'image/webp'):
                raise HTTPException(415, 'image_content_type')
            if product_type and product_type not in runner.types:
                raise HTTPException(422, 'unknown_product_type')
            preview = request.url.path == '/v1/enhance'
            if preview and not config.get('enhancer_model'): raise HTTPException(503,'enhancer_disabled')
            if preview and runner.lock.locked(): raise HTTPException(429,'search_busy')
            active_subjects.add(subject)
            busy = Path(config['jobs']) / 'query-active' if config.get('jobs') else None
            if busy: busy.touch()
            try:
                if preview:
                    return await runner.search(body, product_type, request, operation_kind='enhance')
                result = await runner.search(body, product_type, request)
                from .enhance import needs_fallback,merge
                enabled = config.get('enhancer_model') and enhancement != 'off' and (config.get('enhancer_auto',False) or enhancement == 'force')
                fallback = enabled and (enhancement == 'force' or needs_fallback(result))
                result['enhancement']={'version':'enhancer-1.1','status':'original','automatic':bool(config.get('enhancer_auto',False))}
                # Do not start expensive optional work ahead of another employee.
                if fallback and runner.capacity.active == 1 and not runner.lock.locked() and time.monotonic()-request_started<=4:
                    started_enhance=time.monotonic()
                    try:
                        processed=await runner.search(body,product_type,request,operation_kind='enhance-search',check_context=result|{'enhancement_force':enhancement=='force'})
                        if all(v['index_version']==result['index_version'] for _,v in processed['variants']):
                            result=merge(result,processed['variants'])
                            result['enhancement']=dict(processed['enhancement'],status='processed',automatic=bool(config.get('enhancer_auto',False)))
                        else:result['enhancement']['status']='index_changed_original_used'
                    except (TimeoutError,BrokenPipeError,EOFError,RuntimeError):
                        result['enhancement']['status']='unavailable_original_used'
                    except HTTPException as error:
                        if error.status_code==499:raise
                        result['enhancement']['status']='unavailable_original_used'
                    result['timings_ms']['enhancement_total']=(time.monotonic()-started_enhance)*1000
                elif fallback:result['enhancement']['status']='busy_original_used' if runner.capacity.active!=1 or runner.lock.locked() else 'budget_original_used'
            finally:
                active_subjects.discard(subject)
                if busy and not active_subjects:
                    busy.with_name('query-last').touch();busy.unlink(missing_ok=True)
            body = None
            now = time.monotonic()
            for key in list(cache):
                if cache[key][0] < now:
                    del cache[key]
            if len(cache) >= 32:
                del cache[next(iter(cache))]
            cursor = secrets.token_hex(16)
            cache[cursor] = (now+90, subject, result)  # Metadata only; query bytes never cached.
            return page(result, cursor)
        except TimeoutError:
            raise HTTPException(504, 'search_timeout') from None
        except (BrokenPipeError, EOFError, RuntimeError):
            raise HTTPException(503, 'compute_unavailable') from None
        except asyncio.CancelledError:
            raise HTTPException(499, 'cancelled') from None
        finally:
            runner.capacity.leave()
            if not runner.ready and (recovery is None or recovery.done()):
                recovery = asyncio.create_task(runner.start())

    app.state.runner = runner
    return app
