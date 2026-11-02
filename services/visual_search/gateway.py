"""Same-origin gateway. Existing profile session, no legacy imports or shared DB."""
import asyncio
from contextlib import asynccontextmanager
import ssl
import time
from urllib.parse import urlencode, urlsplit
import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from .protocol import Capacity, read_body, signed


def create_gateway(config, *, auth_transport=None, worker_transport=None):
    origin = config['origin'].rstrip('/')
    worker = config['worker_url'].rstrip('/')
    lab = config.get('synthetic_lab') is True
    if urlsplit(origin).scheme != 'https' and not (lab and urlsplit(origin).hostname in ('127.0.0.1', 'localhost')):
        raise ValueError('https_origin_required')
    if urlsplit(worker).scheme != 'https' and not (lab and urlsplit(worker).hostname in ('127.0.0.1', 'localhost')):
        raise ValueError('verified_worker_tls_required')
    key = bytes.fromhex(config['key_hex'])
    if len(key) < 32:
        raise ValueError('service_key_required')
    profile = config.get('profile_url', 'http://127.0.0.1:8000/api/auth/profile')
    if urlsplit(profile).hostname not in ('127.0.0.1', 'localhost') or urlsplit(profile).path != '/api/auth/profile':
        raise ValueError('local_profile_only')
    capacity = Capacity(3)
    failures, retry_at = 0, 0.
    auth_client = httpx.AsyncClient(transport=auth_transport, trust_env=False, timeout=2, follow_redirects=False)
    verify = ssl.create_default_context(cafile=config['ca_file']) if config.get('ca_file') else True
    worker_client = httpx.AsyncClient(transport=worker_transport, trust_env=False, verify=verify, timeout=7.5, follow_redirects=False,
                                    limits=httpx.Limits(max_connections=3, max_keepalive_connections=3))

    @asynccontextmanager
    async def lifespan(app):
        yield
        await auth_client.aclose()
        await worker_client.aclose()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def no_store(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    async def employee(request):
        if not config.get('enabled', False):
            raise HTTPException(503, 'feature_disabled')
        if request.headers.get('sec-fetch-site') == 'cross-site':
            raise HTTPException(403, 'same_origin_required')
        if request.method == 'POST' and request.headers.get('origin') != origin:
            raise HTTPException(403, 'same_origin_required')
        cookie = request.headers.get('cookie', '')
        if not cookie or len(cookie) > 8192:
            raise HTTPException(401, 'session_required')
        try:
            response = await auth_client.get(profile, headers={'Cookie': cookie})
            if response.status_code != 200:
                raise HTTPException(401, 'session_required')
            value = response.json()
            if not value.get('is_active') or not isinstance(value.get('id'), int) or value['id'] < 1:
                raise HTTPException(403, 'active_employee_required')
            return str(value['id'])
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, 'session_check_unavailable') from None

    async def forward(request, path, body=b''):
        nonlocal failures, retry_at
        subject = await employee(request)
        if retry_at > time.monotonic():
            raise HTTPException(503, 'service_unavailable')
        headers = signed(key, request.method, path, subject, body)
        if body:
            headers['Content-Type'] = request.headers.get('content-type', '')
        try:
            response = await worker_client.request(request.method, worker + path, content=body, headers=headers)
            if response.status_code >= 500:
                raise httpx.ConnectError('worker_unavailable')
            if response.status_code >= 400:
                raise HTTPException(response.status_code, 'search_rejected')
            failures = 0
            return response.json()
        except (httpx.HTTPError, ValueError):
            failures += 1
            if failures >= 3:
                retry_at = time.monotonic()+15
            raise HTTPException(503, 'service_unavailable') from None

    @app.get('/api/visual-search/capabilities')
    async def capabilities(request: Request):
        return await forward(request, '/v1/capabilities')

    @app.get('/api/visual-search/results')
    async def results(request: Request, cursor: str = Query(pattern='^[a-f0-9]{32}$'), offset: int = Query(0, ge=0, le=200000)):
        capacity.enter()
        try:
            return await forward(request, '/v1/results?' + urlencode({'cursor': cursor, 'offset': offset}))
        finally:
            capacity.leave()

    @app.post('/api/visual-search/search')
    async def search(request: Request, product_type: str = Query(min_length=1, max_length=2000)):
        capacity.enter()
        try:
            # Authenticate before accepting an image body; forward rechecks the current session.
            await employee(request)
            if request.headers.get('content-type') not in ('image/jpeg', 'image/png', 'image/webp'):
                raise HTTPException(415, 'image_content_type')
            body = await read_body(request)
            task = asyncio.create_task(forward(request, '/v1/search?' + urlencode({'product_type': product_type}), body))
            try:
                async with asyncio.timeout(8):
                    while not task.done():
                        if await request.is_disconnected():
                            raise HTTPException(499, 'cancelled')
                        await asyncio.sleep(.02)
                    return await task
            except TimeoutError:
                raise HTTPException(504, 'search_timeout') from None
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                body = None
        finally:
            capacity.leave()

    return app
