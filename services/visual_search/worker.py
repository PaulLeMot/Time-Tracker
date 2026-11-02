"""One warmed compute subprocess; bounded admission and hard execution deadline."""
import asyncio
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


def compute(connection, index, model, resources):
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
        connection.send(('ready', list(engine.types), engine.index_id))
        while True:
            body, kind = connection.recv()
            try:
                result = engine.search(body, kind)
                connection.send(('ok', result))
            except ValueError:
                connection.send(('error', 'invalid_image_or_type'))
            finally:
                body = None
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
        self.lock, self.capacity = asyncio.Lock(), Capacity(3)
        self.ready, self.types, self.index = False, [], None
        self.error = None

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
        self.process = context.Process(target=compute, args=(child, self.config['index'], self.config['model'], self.config.get('resources', {})), daemon=True)
        self.process.start()
        child.close()
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and self.process.is_alive():
            if parent.poll():
                message = parent.recv()
                if message[0] == 'ready':
                    self.ready, self.types, self.index = True, message[1], message[2]
                    self.error = None
                    return
                self.error = message[1:] if len(message) > 1 else 'compute_init_failed'
                break
            await asyncio.sleep(.02)
        self.stop()

    async def search(self, body, kind, request):
        started = time.monotonic()
        async with asyncio.timeout(7):
            async with self.lock:
                if not self.ready or not self.process.is_alive():
                    self.stop()
                    raise HTTPException(503, 'warming_or_unavailable')
                if await request.is_disconnected():
                    raise HTTPException(499, 'cancelled')
                queued = (time.monotonic() - started) * 1000
                async def exchange():
                    await asyncio.to_thread(self.pipe.send, (body, kind))
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

    @app.middleware('http')
    async def no_store(request, call_next):
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
        return {'api_version': 1, 'product_types': runner.types, 'index_version': runner.index, 'max_body': 2 * 1024 * 1024}

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

    @app.post('/v1/search')
    async def search(request: Request, product_type: str = Query(min_length=1, max_length=2000)):
        nonlocal recovery
        runner.capacity.enter()
        try:
            body = await read_body(request)
            subject = auth.check(request, body)
            if request.headers.get('content-type') not in ('image/jpeg', 'image/png', 'image/webp'):
                raise HTTPException(415, 'image_content_type')
            if product_type not in runner.types:
                raise HTTPException(422, 'unknown_product_type')
            result = await runner.search(body, product_type, request)
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
