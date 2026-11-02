"""Incremental catalogue asset index, compatible with the existing warmed worker."""
from pathlib import Path
import hashlib, json, os, re, time
import numpy as np
from .engine import Embedder, Engine, VERSION, digest, local_features
from .views import VERSION as VIEWS_VERSION, profile, read_source, representations, safe_source, view_key


def atomic_json(path, value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+str(os.getpid())+'.tmp')
    with temporary.open('w',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,sort_keys=True);stream.flush();os.fsync(stream.fileno())
    deadline=time.monotonic()+3
    while True:
        try:
            os.replace(temporary,path);break
        except OSError as error:
            if getattr(error,'winerror',None) not in (5,32,33) or time.monotonic()>=deadline:raise
            time.sleep(.025)


def build(rows, roots, index_root, model_root, profiles=None, *, progress=lambda x:None, cancelled=lambda:False, throttle=lambda:None, publish=False, embedder=None, seed_cache=None):
    target=Path(index_root);target.mkdir(parents=True,exist_ok=True)
    embed=embedder or Embedder(model_root); cache=target/('cache-'+VIEWS_VERSION);cache.mkdir(exist_ok=True)
    flat=[];features=[];ids={};skipped=[];assets_count=0;seen=set();started=time.monotonic()
    if not isinstance(rows,list) or len(rows)>100000:raise ValueError('catalogue_limit')
    for number,row in enumerate(rows):
        if cancelled():raise ValueError('cancelled')
        code=row.get('code');namespace=row.get('namespace','portal')
        if not isinstance(code,str) or not re.fullmatch('[0-9]{5}',code) or (namespace,code) in seen:raise ValueError('duplicate_or_invalid_code')
        if namespace not in ('portal','operkontur') or any(not isinstance(row.get(k),str) or not row[k].strip() or len(row[k])>2000 for k in ('name','product_type')):raise ValueError('catalogue_metadata')
        seen.add((namespace,code));settings=profile((profiles or {}).get(row.get('kind_key'),{}))
        assets=row.get('assets',[])
        if not isinstance(assets,list) or len(assets)>12:raise ValueError('asset_limit')
        prior_count=len(flat)
        for asset in assets:
            try:
                path=safe_source(roots,asset['root'],asset['relative'])
                image,sha,pixels=read_source(path)
                if asset.get('sha256') and sha!=asset['sha256']:raise ValueError('source_changed')
                selected=profile(asset.get('profile',settings));count=0
                for view,derived in representations(image,selected):
                    count+=1
                    if count>9:raise ValueError('view_budget')
                    key=view_key(sha,view,selected,embed.model_hash)
                    if key not in ids:
                        if cancelled():raise ValueError('cancelled')
                        stored=cache/(key+'.npz')
                        seed=Path(seed_cache)/(sha+'.npz') if seed_cache and view['transform']=='identity' else None
                        if not stored.is_file() and seed and seed.is_file():
                            import shutil
                            shutil.copyfile(seed,stored)
                        if stored.is_file():
                            if len(features)%128==0:throttle()
                            with np.load(stored,allow_pickle=False) as value:feature=tuple(value[n].copy() for n in ('points','descriptors','vector'))
                        else:
                            throttle()
                            derived.thumbnail((1024,1024));points,desc=local_features(derived);vector=embed(derived);feature=(points,desc,vector)
                            tmp=stored.with_suffix('.tmp')
                            with tmp.open('wb') as output:np.savez(output,points=points,descriptors=desc,vector=vector)
                            os.replace(tmp,stored)
                        ids[key]=len(features);features.append((stored,len(feature[0])))
                    flat.append({k:row.get(k) for k in ('code','name','product_type','fandom','kind_key','source_key','record_version','is_kit','standalone','components','composition_complete')} |
                                {'namespace':namespace,'feature':ids[key],'sha256':sha,'pixel_sha256':pixels,'asset_id':asset.get('id',sha),'asset_role':asset.get('role','catalogue'),
                                 'view':view,'profile':selected,'source_status':asset.get('source_status','500'),'source_ref':{'root':asset['root'],'relative':asset['relative']}})
                assets_count+=1
            except (OSError,ValueError,KeyError) as error:
                if str(error)=='cancelled':raise
                skipped.append({'code':code,'asset_id':asset.get('id'),'reason':str(error) if isinstance(error,ValueError) else 'source_unavailable'})
        if len(flat)==prior_count:
            flat.append({k:row.get(k) for k in ('code','name','product_type','fandom','kind_key','source_key','record_version','is_kit','standalone','components','composition_complete')} |
                        {'namespace':namespace,'feature':-1,'sha256':'','source_status':'waiting_for_image'})
        progress({'processed':number+1,'total':len(rows),'assets':assets_count,'views':len(flat),'seconds':round(time.monotonic()-started,2)})
    if not features:raise ValueError('empty_index')
    generation='index-'+str(time.time_ns());out=target/generation;out.mkdir()
    offsets=np.cumsum([0]+[x[1] for x in features],dtype='int64')
    arrays={name:np.lib.format.open_memmap(out/(name+'.npy'),mode='w+',dtype=dtype,shape=shape) for name,dtype,shape in (
        ('vectors','float32',(len(features),384)),('points','float32',(int(offsets[-1]),2)),('descriptors','uint8',(int(offsets[-1]),128)))}
    for n,(stored,_) in enumerate(features):
        with np.load(stored,allow_pickle=False) as item:
            arrays['vectors'][n]=item['vector'];arrays['points'][offsets[n]:offsets[n+1]]=item['points'];arrays['descriptors'][offsets[n]:offsets[n+1]]=item['descriptors']
    for array in arrays.values():array.flush();array._mmap.close()
    np.save(out/'offsets.npy',offsets,allow_pickle=False)
    atomic_json(out/'products.json',flat)
    scopes={scope:{'products':len({r['code'] for r in flat if r['namespace']==scope}),
                  'source_images':len({r.get('asset_id') for r in flat if r['namespace']==scope and r['feature']>=0}),
                  'views':sum(r['feature']>=0 for r in flat if r['namespace']==scope),
                  'features':len({r['feature'] for r in flat if r['namespace']==scope and r['feature']>=0}),
                  'kit_links':sum(len(r.get('components') or []) for r in rows if r.get('namespace','portal')==scope)} for scope in ('portal','operkontur')}
    meta={'version':VERSION,'schema':2,'views_version':VIEWS_VERSION,'model_hash':embed.model_hash,'dimension':384,'products':len(flat),'unique_images':len(features),
          'unique_products':len({(r['namespace'],r['code']) for r in flat}),'source_images':len({r.get('asset_id') for r in flat if r['feature']>=0}),'asset_associations':assets_count,'view_count':sum(r['feature']>=0 for r in flat),'namespaces':scopes,'kit_links':sum(len(r.get('components') or []) for r in rows),'skipped':skipped,
          'catalogue_hash':hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'created_epoch':time.time(),
          'files':{p.name:digest(p) for p in out.iterdir() if p.is_file()}}
    atomic_json(out/'manifest.json',meta);checked=Engine(out,model_root,embedder=embed);checked.close()
    pointer={'generation':generation,'sha256':digest(out/'manifest.json')}
    if publish:activate(target,pointer,model_root,embedder=embed)
    return {'pointer':pointer,'manifest':meta}


def activate(root,pointer,model_root,embedder=None):
    root=Path(root)
    if set(pointer)!={'generation','sha256'} or not re.fullmatch('index-[0-9]+',pointer['generation']):raise ValueError('index_pointer')
    path=root/pointer['generation']
    if path.is_symlink() or digest(path/'manifest.json')!=pointer['sha256']:raise ValueError('index_pointer_checksum')
    checked=Engine(path,model_root,embedder=embedder);checked.close()
    if (root/'current.json').exists():atomic_json(root/'previous.json',json.loads((root/'current.json').read_text('utf-8')))
    atomic_json(root/'current.json',pointer)
