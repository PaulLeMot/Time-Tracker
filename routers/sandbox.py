from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime, date
from typing import List, Optional
from pydantic import BaseModel
from database import get_db
import crud
from models import Deal, DealProduct, Notification, NotificationType, NotificationStatus, Employee, TaskType, Task, DealType
from routers.auth import get_current_admin, get_current_employee
from sse import notify_admin_clients, notify_employee

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])

# ==================== СХЕМЫ ====================
class DealTypeResponse(BaseModel):
    id: int
    code: str
    name: str

class ClientResponse(BaseModel):
    id: int
    code: str
    name: str

class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]

# Новые схемы для товаров сделки
class DealProductCreate(BaseModel):
    name: str
    tech_card: Optional[List[str]] = []   # список этапов

class DealProductResponse(BaseModel):
    id: int
    name: str
    tech_card: Optional[List[str]]

class DealCreate(BaseModel):
    title: str
    deal_type_id: int
    client_id: int
    planned_date: date
    products: List[DealProductCreate]   # теперь товары без привязки к глобальному каталогу

class DealResponse(BaseModel):
    id: int
    title: str
    deal_type: DealTypeResponse
    client: ClientResponse
    planned_date: date
    status: str
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int]
    updated_by: Optional[int]
    products: List[DealProductResponse]   # товары сделки
    logistics_status: str
    logistics_address: Optional[str]
    logistics_departure: Optional[datetime]
    logistics_arrival: Optional[datetime]
    logistics_route: Optional[str]

# ==================== ЭНДПОИНТЫ ====================

@router.get("/deal-types", response_model=List[DealTypeResponse])
async def get_deal_types(db: AsyncSession = Depends(get_db)):
    return await crud.get_deal_types(db)

@router.get("/clients", response_model=List[ClientResponse])
async def get_clients(db: AsyncSession = Depends(get_db)):
    return await crud.get_clients(db)

@router.get("/roles", response_model=List[RoleResponse])
async def get_roles(db: AsyncSession = Depends(get_db)):
    return await crud.get_roles(db)

@router.post("/deals", response_model=DealResponse, status_code=201)
async def create_deal(
    data: DealCreate,
    admin: Employee = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    # Преобразуем продукты в формат, который ждёт crud.create_deal
    products_data = [{"name": p.name, "tech_card": p.tech_card} for p in data.products]
    deal = await crud.create_deal(
        db=db,
        title=data.title,
        deal_type_id=data.deal_type_id,
        client_id=data.client_id,
        planned_date=data.planned_date,
        created_by=admin.id,
        products=products_data
    )
    return await get_deal_response(deal.id, db)

@router.get("/deals", response_model=List[DealResponse])
async def list_deals(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    deals = await crud.get_deals(db, status, skip, limit)
    result = []
    for d in deals:
        result.append(await get_deal_response(d.id, db))
    return result

@router.get("/deals/{deal_id}", response_model=DealResponse)
async def get_deal(deal_id: int, db: AsyncSession = Depends(get_db)):
    return await get_deal_response(deal_id, db)

@router.put("/deals/{deal_id}")
async def update_deal(
    deal_id: int,
    title: Optional[str] = None,
    planned_date: Optional[date] = None,
    admin: Employee = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    updates = {}
    if title is not None:
        updates["title"] = title
    if planned_date is not None:
        updates["planned_date"] = planned_date
    if updates:
        updates["updated_by"] = admin.id
        await crud.update_deal(db, deal_id, **updates)
    return {"status": "ok"}

@router.delete("/deals/{deal_id}", status_code=204)
async def delete_deal(
    deal_id: int,
    admin: Employee = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    await crud.delete_deal(db, deal_id)
    return None

# ==================== ЛОГИСТИКА (оставлена) ====================

@router.post("/deals/{deal_id}/logistics/depart")
async def logistics_depart(
    deal_id: int,
    address: str,
    route: str,
    employee: Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    deal = await crud.get_deal_by_id(db, deal_id)
    if not deal:
        raise HTTPException(404, "Сделка не найдена")
    await crud.update_deal_logistics(
        db,
        deal_id,
        logistics_status="in_transit",
        logistics_address=address,
        logistics_route=route,
        logistics_departure=datetime.now()
    )
    await notify_admin_clients()
    return {"status": "ok"}

@router.post("/deals/{deal_id}/logistics/arrive")
async def logistics_arrive(
    deal_id: int,
    employee: Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    deal = await crud.get_deal_by_id(db, deal_id)
    if not deal:
        raise HTTPException(404, "Сделка не найдена")
    if deal.logistics_status != "in_transit":
        raise HTTPException(400, "Логистика не в пути")
    await crud.update_deal_logistics(
        db,
        deal_id,
        logistics_status="delivered",
        logistics_arrival=datetime.now(),
        status="completed"
    )
    await notify_admin_clients()
    return {"status": "ok"}

# ==================== ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ====================
async def get_deal_response(deal_id: int, db: AsyncSession):
    deal = await crud.get_deal_with_details(db, deal_id)
    if not deal:
        raise HTTPException(404, "Сделка не найдена")

    products = []
    for dp in deal.deal_products:
        products.append({
            "id": dp.id,
            "name": dp.name,
            "tech_card": dp.tech_card if dp.tech_card else []
        })

    return DealResponse(
        id=deal.id,
        title=deal.title,
        deal_type={"id": deal.deal_type.id, "code": deal.deal_type.code, "name": deal.deal_type.name},
        client={"id": deal.client.id, "code": deal.client.code, "name": deal.client.name},
        planned_date=deal.planned_date,
        status=deal.status.value,
        created_at=deal.created_at,
        updated_at=deal.updated_at,
        created_by=deal.created_by,
        updated_by=deal.updated_by,
        products=products,
        logistics_status=deal.logistics_status.value,
        logistics_address=deal.logistics_address,
        logistics_departure=deal.logistics_departure,
        logistics_arrival=deal.logistics_arrival,
        logistics_route=deal.logistics_route
    )

# ==================== ТИПЫ ЗАДАЧ (оставлены) ====================

@router.get("/task-types", response_model=List[dict])
async def get_task_types(db: AsyncSession = Depends(get_db)):
    types = await crud.get_task_types(db)
    return [{"id": t.id, "name": t.name} for t in types]

@router.post("/task-types", status_code=201, response_model=dict)
async def create_task_type(
    name: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db)
):
    task_type = await crud.create_task_type(db, name)
    return {"id": task_type.id, "name": task_type.name}

@router.delete("/task-types/{type_id}", status_code=204)
async def delete_task_type(
    type_id: int,
    db: AsyncSession = Depends(get_db)
):
    await crud.delete_task_type(db, type_id)
    return None

# ==================== ЗАДАЧИ (оставлены) ====================

@router.get("/tasks", response_model=List[dict])
async def get_tasks(db: AsyncSession = Depends(get_db)):
    tasks = await crud.get_tasks(db)
    return [
        {
            "id": t.id,
            "name": t.name,
            "type_id": t.type_id,
            "type_name": t.type.name if t.type else None
        }
        for t in tasks
    ]

@router.post("/tasks", status_code=201, response_model=dict)
async def create_task(
    name: str = Body(..., embed=True),
    type_id: int = Body(..., embed=True),
    db: AsyncSession = Depends(get_db)
):
    task = await crud.create_task(db, name, type_id)
    return {"id": task.id, "name": task.name, "type_id": task.type_id}

@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db)
):
    await crud.delete_task(db, task_id)
    return None

# ==================== ИП и МП (оставлены) ====================
class IPResponse(BaseModel):
    id: int
    name: str

class IPCreate(BaseModel):
    name: str

@router.get("/ips", response_model=List[IPResponse])
async def get_ips(db: AsyncSession = Depends(get_db)):
    ips = await crud.get_ips(db)
    return [{"id": i.id, "name": i.name} for i in ips]

@router.post("/ips", status_code=201, response_model=IPResponse)
async def create_ip(data: IPCreate, db: AsyncSession = Depends(get_db)):
    ip = await crud.create_ip(db, data.name)
    return {"id": ip.id, "name": ip.name}

@router.delete("/ips/{ip_id}", status_code=204)
async def delete_ip(ip_id: int, db: AsyncSession = Depends(get_db)):
    await crud.delete_ip(db, ip_id)
    return None

class MPResponse(BaseModel):
    id: int
    name: str

class MPCreate(BaseModel):
    name: str

@router.get("/mps", response_model=List[MPResponse])
async def get_mps(db: AsyncSession = Depends(get_db)):
    mps = await crud.get_mps(db)
    return [{"id": m.id, "name": m.name} for m in mps]

@router.post("/mps", status_code=201, response_model=MPResponse)
async def create_mp(data: MPCreate, db: AsyncSession = Depends(get_db)):
    mp = await crud.create_mp(db, data.name)
    return {"id": mp.id, "name": mp.name}

@router.delete("/mps/{mp_id}", status_code=204)
async def delete_mp(mp_id: int, db: AsyncSession = Depends(get_db)):
    await crud.delete_mp(db, mp_id)
    return None

@router.delete("/deal-types/{type_id}", status_code=204)
async def delete_deal_type(type_id: int, db: AsyncSession = Depends(get_db)):
    await crud.delete_deal_type(db, type_id)
    return None

class DealTypeCreate(BaseModel):
    name: str

class DealTypeUpdate(BaseModel):
    name: str

@router.post("/deal-types", status_code=201, response_model=DealTypeResponse)
async def create_deal_type(data: DealTypeCreate, db: AsyncSession = Depends(get_db)):
    try:
        deal_type = await crud.create_deal_type(db, data.name)
    except Exception as e:
        raise HTTPException(400, str(e))
    return deal_type

@router.put("/deal-types/{type_id}", response_model=DealTypeResponse)
async def update_deal_type(type_id: int, data: DealTypeUpdate, db: AsyncSession = Depends(get_db)):
    try:
        deal_type = await crud.update_deal_type(db, type_id, data.name)
    except Exception as e:
        raise HTTPException(400, str(e))
    return deal_type

# Схемы для справочника товаров
class CatalogProductCreate(BaseModel):
    name: str
    tech_card: Optional[List[str]] = []

class CatalogProductUpdate(BaseModel):
    name: Optional[str] = None
    tech_card: Optional[List[str]] = None

# Эндпоинты
@router.get("/deal-products", response_model=List[DealProductResponse])
async def get_deal_products(db: AsyncSession = Depends(get_db)):
    stmt = select(DealProduct)
    result = await db.execute(stmt)
    products = result.scalars().all()
    return [{"id": p.id, "name": p.name, "tech_card": p.tech_card or []} for p in products]

@router.post("/deal-products", status_code=201, response_model=DealProductResponse)
async def create_deal_product(data: CatalogProductCreate, db: AsyncSession = Depends(get_db)):
    product = DealProduct(name=data.name, tech_card=data.tech_card)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return {"id": product.id, "name": product.name, "tech_card": product.tech_card or []}

@router.put("/deal-products/{product_id}", response_model=DealProductResponse)
async def update_deal_product(
    product_id: int,
    data: CatalogProductUpdate,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(DealProduct).where(DealProduct.id == product_id)
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")
    if data.name is not None:
        product.name = data.name
    if data.tech_card is not None:
        product.tech_card = data.tech_card
    await db.commit()
    await db.refresh(product)
    return {"id": product.id, "name": product.name, "tech_card": product.tech_card or []}

@router.delete("/deal-products/{product_id}", status_code=204)
async def delete_deal_product(product_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(DealProduct).where(DealProduct.id == product_id)
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")
    await db.delete(product)
    await db.commit()
    return None