"""A narrow signed endpoint; the existing /api/products/import remains unchanged."""
from pathlib import Path
import os
from fastapi import APIRouter,Depends,HTTPException,Request
from sqlalchemy import select,text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models import Product
from operkontur_images_sync import VERSION,MAX_BODY,SyncError,authenticate,parse,eligible,changes

router=APIRouter(prefix='/api/integrations/operkontur/images',tags=['operkontur-images'])

@router.post('/sync')
async def synchronize(request:Request,db:AsyncSession=Depends(get_db)):
    body=bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body)>MAX_BODY:raise HTTPException(413,'Payload too large')
    try:secret=Path(os.getenv('OPERKONTUR_IMAGES_KEY_FILE','/app/.operkontur-images.key')).read_bytes()
    except OSError:raise HTTPException(503,'Integration is not configured') from None
    try:authenticate(secret,request.headers.get('x-operkontur-time'),request.headers.get('x-operkontur-signature'),bytes(body))
    except SyncError:raise HTTPException(401,'Invalid integration authentication') from None
    try:value=parse(body)
    except SyncError as e:raise HTTPException(422,str(e)) from None
    # Verification is read-only. Never register a missing or different image.
    from starlette.concurrency import run_in_threadpool
    rows,rejected=await run_in_threadpool(eligible,value['products'],os.getenv('OPERKONTUR_IMAGES_ROOT','/app/static/img'))
    try:
        # Serializes against the old manual DELETE/import without modifying that route.
        await db.execute(text('SET LOCAL lock_timeout = \'5s\''))
        await db.execute(text('LOCK TABLE products IN SHARE ROW EXCLUSIVE MODE'))
        result=await db.execute(select(Product).where(Product.code.in_([r['code'] for r in rows])))
        existing={p.code:{k:getattr(p,k) for k in ('product_type','fandom','name')} for p in result.scalars()}
        counts,changed=changes(rows,existing)
        for start in range(0,len(changed),500):
            stmt=insert(Product).values(changed[start:start+500])
            await db.execute(stmt.on_conflict_do_update(index_elements=[Product.code],set_={k:getattr(stmt.excluded,k) for k in ('product_type','fandom','name')}))
        await db.commit()
    except Exception:
        await db.rollback();raise HTTPException(503,'Catalog synchronization failed; retry later') from None
    return {'version':VERSION,'job_id':value['job_id'],'status':'partial' if rejected else 'complete',
            **counts,'rejected':rejected,'received':len(value['products'])}
