from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func, or_
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

class FilterOptionsOut(BaseModel):
    product_types: List[str]
    fandoms: List[str]

class FilteredProductsOut(BaseModel):
    items: List[ProductOut]
    total: int

# ----------------------------------------------------------------------
# 1. Получение уникальных значений для выпадающих списков (видов и фандомов)
# ----------------------------------------------------------------------
@router.get("/filter-options", response_model=FilterOptionsOut)
async def get_filter_options(db: AsyncSession = Depends(get_db)):
    # Получаем уникальные product_type
    stmt_types = select(Product.product_type).distinct().where(Product.product_type.isnot(None)).order_by(Product.product_type)
    result_types = await db.execute(stmt_types)
    product_types = [row[0] for row in result_types.all() if row[0]]
    
    # Получаем уникальные fandom
    stmt_fandoms = select(Product.fandom).distinct().where(Product.fandom.isnot(None)).order_by(Product.fandom)
    result_fandoms = await db.execute(stmt_fandoms)
    fandoms = [row[0] for row in result_fandoms.all() if row[0]]
    
    return FilterOptionsOut(product_types=product_types, fandoms=fandoms)


# ----------------------------------------------------------------------
# 2. Фильтрованный поиск с пагинацией (основной эндпоинт для фронта)
# ----------------------------------------------------------------------
@router.get("/filtered", response_model=FilteredProductsOut)
async def get_filtered_products(
    code: Optional[str] = Query(None, description="Поиск по коду (часть)"),
    product_type: Optional[str] = Query(None, description="Тип товара"),
    fandom: Optional[str] = Query(None, description="Фандом"),
    limit: int = Query(30, ge=1, le=100, description="Количество на странице"),
    offset: int = Query(0, ge=0, description="Смещение (пагинация)"),
    db: AsyncSession = Depends(get_db)
):
    # Базовый запрос
    query = select(Product)
    
    # Применяем фильтры
    if code and code.strip():
        query = query.where(Product.code.ilike(f"%{code.strip()}%"))
    if product_type:
        query = query.where(Product.product_type == product_type)
    if fandom:
        query = query.where(Product.fandom == fandom)
    
    # Сортировка для стабильности
    query = query.order_by(Product.code)
    
    # Считаем общее количество (для пагинации)
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    # Применяем пагинацию
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    products = result.scalars().all()
    
    items = [
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
    
    return FilteredProductsOut(items=items, total=total)


# ----------------------------------------------------------------------
# 3. Поиск по одному товару по коду (оставляем как есть)
# ----------------------------------------------------------------------
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