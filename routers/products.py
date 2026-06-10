from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models import Product, Employee
from typing import List, Optional
from pydantic import BaseModel
import pandas as pd
import re
from routers.auth import get_current_admin

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
# 1. Получение уникальных значений для выпадающих списков
# ----------------------------------------------------------------------
@router.get("/filter-options", response_model=FilterOptionsOut)
async def get_filter_options(
    product_type: Optional[str] = Query(None, description="Выбранный тип товара (для фильтрации фандомов)"),
    fandom: Optional[str] = Query(None, description="Выбранный фандом (для фильтрации типов)"),
    db: AsyncSession = Depends(get_db)
):
    stmt_types = select(Product.product_type).distinct().where(Product.product_type.isnot(None))
    stmt_fandoms = select(Product.fandom).distinct().where(Product.fandom.isnot(None))

    if product_type:
        stmt_fandoms = stmt_fandoms.where(Product.product_type == product_type)
    if fandom:
        stmt_types = stmt_types.where(Product.fandom == fandom)

    stmt_types = stmt_types.order_by(Product.product_type)
    stmt_fandoms = stmt_fandoms.order_by(Product.fandom)

    result_types = await db.execute(stmt_types)
    product_types = [row[0] for row in result_types.all() if row[0]]

    result_fandoms = await db.execute(stmt_fandoms)
    fandoms = [row[0] for row in result_fandoms.all() if row[0]]

    return FilterOptionsOut(product_types=product_types, fandoms=fandoms)

# ----------------------------------------------------------------------
# 2. Фильтрованный поиск с пагинацией
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
    query = select(Product)

    if code and code.strip():
        query = query.where(Product.code.ilike(f"%{code.strip()}%"))
    if product_type:
        query = query.where(Product.product_type == product_type)
    if fandom:
        query = query.where(Product.fandom == fandom)

    query = query.order_by(Product.name)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

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
# 3. Поиск по коду
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

# ----------------------------------------------------------------------
# 4. Импорт товаров из Excel (только для администратора)
# ----------------------------------------------------------------------
@router.post("/import", status_code=200)
async def import_products(
    admin: Employee = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    try:
        # 1. Удаляем старые записи
        await db.execute(delete(Product))

        # 2. Читаем Excel, все столбцы как строки
        df = pd.read_excel('/app/import_data/img.xlsx', dtype=str)
        df.columns = ['code', 'product_type', 'fandom', 'name']

        # 3. Очистка кода: оставляем ТОЛЬКО цифры (удаляем все невидимые символы и буквы)
        df['code'] = df['code'].apply(
            lambda x: re.sub(r'[^\d]', '', str(x)) if pd.notna(x) else ''
        )

        # 4. Удаление строк с пустым кодом
        df = df[df['code'] != '']

        # 5. Очистка остальных столбцов (неразрывные пробелы и обрезка)
        for col in ['product_type', 'fandom', 'name']:
            df[col] = df[col].astype(str).str.replace('\u00a0', ' ', regex=False).str.strip()
            df[col] = df[col].replace({'nan': None, 'None': None, '': None})

        # 6. Удаление дубликатов по коду
        dup_count = df.duplicated(subset=['code'], keep=False).sum()
        if dup_count:
            print(f"⚠️ Найдено {dup_count} строк с дублирующимися кодами. Оставлены первые вхождения.")
        df = df.drop_duplicates(subset=['code'])

        # 7. Вставка
        added = 0
        for _, row in df.iterrows():
            product = Product(
                code=row['code'],
                product_type=row['product_type'] if pd.notna(row['product_type']) else None,
                fandom=row['fandom'] if pd.notna(row['fandom']) else None,
                name=row['name']
            )
            db.add(product)
            added += 1

        await db.commit()
        return {
            "message": f"Импорт успешно завершён администратором {admin.full_name}",
            "count": added,
            "duplicates_removed": dup_count
        }

    except Exception as e:
        await db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ошибка импорта: {str(e)}")