from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models import Product
from typing import List, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/api/products", tags=["products"])

class ProductOut(BaseModel):
    id: int
    code: str
    product_type: str
    fandom: Optional[str] = None
    name: str
    image_url: str

@router.get("/search", response_model=List[ProductOut])
async def search_products(
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Product).where(
        or_(
            Product.code.ilike(f"%{q}%"),
            Product.name.ilike(f"%{q}%"),
            Product.fandom.ilike(f"%{q}%"),
            Product.product_type.ilike(f"%{q}%")
        )
    ).order_by(Product.code)
    result = await db.execute(stmt)
    products = result.scalars().all()

    return [
        ProductOut(
            id=p.id,
            code=p.code,
            product_type=p.product_type,
            fandom=p.fandom,
            name=p.name,
            image_url=f"/static/img/{p.code}.jpg"
        )
        for p in products
    ]

@router.get("/{code}", response_model=ProductOut)
async def get_product_by_code(code: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Product).where(Product.code == code)
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return ProductOut(
        id=product.id,
        code=product.code,
        product_type=product.product_type,
        fandom=product.fandom,
        name=product.name,
        image_url=f"/static/img/{product.code}.jpg"
    )