"""Prepare/check a new isolated Windows x64 restore using only the exact local TOOLS."""
from pathlib import Path
import argparse,json,os,subprocess,sys,time


def prepare(root):
    root=Path(root).resolve(strict=True)
    actions=json.loads((root/'RESTORE_ACTIONS.json').read_text('utf-8'))
    if actions.get('automatic_production_sync') is not False or actions.get('production_tasks_registered') is not False:raise ValueError('isolated_restore_marker_required')
    for name in ('python/python.exe','source/services/visual_search/requirements-windows.lock','model/manifest.json','index/current.json'):
        if not (root/name).is_file():raise ValueError('exact_search_tools_and_state_required')
    if os.name!='nt':raise ValueError('this_tools_bundle_requires_windows_x64')
    # Native wheel headers exceed legacy MAX_PATH under long installation roots.
    if len(str(root))>70 or not str(root).isascii():raise ValueError('short_ascii_restore_path_required')
    venv=root/'venv';log=root/'offline-install.log'
    environment=dict(os.environ,PIP_NO_INDEX='1',PIP_DISABLE_PIP_VERSION_CHECK='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',PYTHONDONTWRITEBYTECODE='1')
    def run(arguments):
        with log.open('ab') as output:subprocess.run([str(x) for x in arguments],env=environment,stdout=output,stderr=output,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    if not (venv/'pyvenv.cfg').exists():run([root/'python/python.exe','-m','venv',venv])
    if not (root/'dependencies.ready').exists():
        run([venv/'Scripts/python.exe','-m','pip','install','--no-index','--disable-pip-version-check','--find-links',root/'wheels','--require-hashes','-r',root/'source/services/visual_search/requirements-windows.lock'])
        (root/'dependencies.ready').write_text('hash-locked local wheels only\n',encoding='ascii')
    return {'status':'OFFLINE_DEPENDENCIES_READY','production_tasks_registered':False,'production_sync':False}


def check(root):
    root=Path(root).resolve(strict=True);sys.path.insert(0,str(root/'source'))
    from .engine import Engine,resolve_index
    started=time.perf_counter();engine=Engine(resolve_index(root/'index'),root/'model');cold=time.perf_counter()-started
    rows=json.loads((root/'catalogue.json').read_text('utf-8'));selected=next(r for r in rows if (root/'images500'/(r['code']+'.jpg')).is_file())
    body=(root/'images500'/(selected['code']+'.jpg')).read_bytes();result=engine.search(body,selected['product_type'])
    if not any(r['code']==selected['code'] for r in result['items'][:5]):raise ValueError('restored_search_not_correct')
    private=engine.search(body,'',namespace='operkontur') if engine.meta.get('schema')==2 else None
    engine.close()
    return {'status':'OFFLINE_MODEL_INDEX_SEARCH_PASS','cold_seconds':round(cold,3),'index_version':result['index_version'],'catalogue_query_top5':True,
            'admin_namespace_search':private is not None,'query_photos_saved':False,'production_tasks_registered':False,'production_sync':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=('prepare','check'));p.add_argument('--root',required=True);a=p.parse_args()
    result=prepare(a.root) if a.command=='prepare' else check(a.root)
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
