"""Loopback-only demo gateway with synthetic auth. Never use as a production launcher."""
import argparse
import json
from pathlib import Path
import httpx
import uvicorn
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from .gateway import create_gateway


def make_lab(config):
    root = Path(config['synthetic_root']).resolve(strict=True)
    if (root/'DATA_CLASS.txt').read_text('utf-8').strip() != 'SYNTHETIC':
        raise ValueError('synthetic_only')
    source = Path(__file__).resolve().parents[2]
    async def profile(request):
        if request.headers.get('cookie') != 'session=SYNTHETIC':
            return httpx.Response(401)
        return httpx.Response(200, json={'id': 97001, 'is_active': True})
    app = create_gateway(config, auth_transport=httpx.MockTransport(profile))
    rows = json.loads(Path(config.get('catalogue', root/'catalogue.json')).read_text('utf-8'))

    @app.get('/api/products/filter-options')
    async def filters():
        return {'product_types': sorted({r['product_type'] for r in rows}), 'fandoms': ['SYNTHETIC']}

    @app.get('/api/products/filtered')
    async def filtered():
        return {'items': [], 'total': 0}

    @app.get('/static/search.html')
    async def page():
        html = (source/'static/search.html').read_text('utf-8').replace('<body class="tt-camera-search">', '<body class="tt-camera-search"><p role="note">Тестовый стенд. Рабочие данные не изменяются.</p>', 1)
        response = HTMLResponse(html, headers={'Cache-Control': 'no-store'})
        response.set_cookie('session', 'SYNTHETIC', httponly=True, samesite='strict')
        return response

    @app.get('/lab/status')
    async def status():
        return {'data_class': 'SYNTHETIC', 'auth': 'stub_for_demo_only'}

    app.mount('/static/img', StaticFiles(directory=config.get('catalogue_images', root/'images')))
    app.mount('/static', StaticFiles(directory=source/'static'))
    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text('utf-8'))
    if config.get('synthetic_lab') is not True or config['origin'] != f"http://127.0.0.1:{config['port']}":
        raise ValueError('loopback_synthetic_only')
    uvicorn.run(make_lab(config), host='127.0.0.1', port=config['port'], access_log=False, log_level='warning')
