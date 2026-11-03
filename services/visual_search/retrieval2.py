"""Best-view retrieval and confirmed membership expansion; never infer kit contents."""
import time
import numpy as np

# Calibration: the tuning set's highest incorrect first result was 0.90399.
# Leave a margin and require local evidence; this score is not a probability.
CONFIRMED_SCORE=.92
VIEW_PENALTY=.03


def search(engine,body,product_type='',mode='hybrid',namespace='portal'):
    from .engine import decode,local_features,geometry,VERSION,RANKING_VERSION
    started=time.perf_counter();image=decode(body);decoded=time.perf_counter()
    qp,qd=local_features(image)
    if mode=='rescue':
        import cv2
        keys,descriptors=cv2.SIFT_create(nfeatures=768).detectAndCompute(cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2GRAY),None)
        qp=np.float32([k.pt for k in keys]).reshape(-1,2);qd=np.zeros((0,128),'uint8') if descriptors is None else descriptors
    vector=engine.embed(image);embedded=time.perf_counter()
    rows=[r for r in engine.rows if r.get('namespace','portal')==namespace]
    products={r['code']:r for r in rows};kits={code:r for code,r in products.items() if r.get('is_kit')}
    eligible={r['code'] for r in rows if not product_type or r['product_type']==product_type}
    component_codes={code for kit in kits.values() if kit['code'] in eligible for code in (kit.get('components') or []) if code in products}
    groups={}
    matching_codes=eligible|component_codes
    for row in rows:
        if row['feature']>=0 and row['code'] in matching_codes:groups.setdefault(row['feature'],[]).append(row)
    candidates=np.array(list(groups),dtype='int64')
    sims=engine.vectors[candidates]@vector if len(candidates) else np.array([])
    items={}
    for i in np.argsort(-sims,kind='stable')[:128 if mode=='rescue' else 48]:
        feature=int(candidates[i]);sim=float(sims[i]);a,b=engine.offsets[feature:feature+2]
        inliers,geo=geometry(qp,qd,engine.points[a:b],engine.descriptors[a:b],strict=True) if mode=='rescue' else geometry(qp,qd,engine.points[a:b],engine.descriptors[a:b]) if mode!='dino' else (0,0.)
        if sim<.60 and not(mode=='rescue' and sim>=.35 and inliers>=18 and geo>=.40):continue
        reciprocal=mode=='rescue'
        if mode not in ('rescue','dino') and inliers>=10 and geo>=.30:
            unique_count,unique_support=geometry(qp,qd,engine.points[a:b],engine.descriptors[a:b],strict=True)
            reciprocal=unique_count>=10 and unique_support>=.30
        # Existing geometry-first bias remains disabled. Shared templates need strong global support.
        for row in groups[feature]:
            score=sim-(VIEW_PENALTY if row.get('view',{}).get('role','whole')!='whole' else 0.)
            if mode=='rescue' and inliers>=18 and geo>=.40:score=max(score,.72+.22*geo)
            calibrated=mode!='rescue' and (row.get('profile',{}).get('revision',1)==1 or row.get('view',{}).get('role','whole')=='whole')
            status='confirmed' if calibrated and reciprocal and inliers>=10 and geo>=.30 and score>=CONFIRMED_SCORE else 'uncertain' if score>=.72 else 'weak'
            code=row['code'];old=items.get(code)
            if old and old['score']>=score:continue
            items[code]={k:row.get(k) for k in ('code','name','product_type','fandom','is_kit','composition_complete')} | {
                'score':round(score,5),'evidence':'geometry' if status=='confirmed' else 'weak','similarity_status':status,
                'geometry_inliers':inliers,'geometry_support':round(geo,5),
                'geometry_reciprocal':reciprocal,
                'match_role':row.get('asset_role','catalogue'),'match_view':row.get('view',{'role':'whole'}),
                'relation':'direct','image_url':'/static/img/'+code+'.jpg','image_500_url':'/api/visual-search/image500/'+code,
                'asset_id':row.get('asset_id'),'_standalone':row.get('standalone',True)}
    expanded={code:item for code,item in items.items() if code in eligible and item['_standalone'] is not False}
    for code,item in items.items():
        for kitcode,kit in kits.items():
            if code not in (kit.get('components') or []):continue
            if product_type and code not in eligible and kitcode not in eligible:continue
            if kitcode not in expanded or expanded[kitcode]['score']<item['score']:
                expanded[kitcode]={k:kit.get(k) for k in ('code','name','product_type','fandom','is_kit','composition_complete')} | {
                    **{k:v for k,v in item.items() if k not in ('code','name','product_type','fandom','is_kit','composition_complete')},
                    'relation':'confirmed_component','component_code':code,'image_url':'/static/img/'+kitcode+'.jpg','image_500_url':'/api/visual-search/image500/'+kitcode}
    result=sorted(expanded.values(),key=lambda x:(-x['score'],x.get('relation')!='direct',x['code']))
    for row in result:row.pop('_standalone',None)
    ended=time.perf_counter()
    return {'api_version':1,'schema_version':2,'index_version':engine.index_id,'model_version':VERSION,'ranking_version':RANKING_VERSION+'-best-view-2.1',
            'status':'similar' if result and result[0]['similarity_status']=='confirmed' else 'weak' if result else 'none','items':result,'total':len(result),'candidate_design_limit':128 if mode=='rescue' else 48,
            'timings_ms':{'decode':(decoded-started)*1000,'features_embedding':(embedded-decoded)*1000,'search_rerank':(ended-embedded)*1000,'compute':(ended-started)*1000}}
