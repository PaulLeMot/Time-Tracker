from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from datetime import datetime, date
from typing import List, Optional
from pydantic import BaseModel
from database import get_db
import crud
from models import Deal, DealProduct, DealProductStage, Notification, NotificationType, NotificationStatus, Employee, TaskType, Task, Product, DealType
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

class StageResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]

class ProductResponse(BaseModel):
    id: int
    name: str
    code: str
    tech_card: Optional[str]

class DealProductCreate(BaseModel):
    product_id: int
    quantity: int

class DealCreate(BaseModel):
    title: str
    deal_type_id: int
    client_id: int
    planned_date: date
    products: List[DealProductCreate]
    product_stages: dict  # {product_id: [stage_id, ...]}

class DealProductStageResponse(BaseModel):
    id: int
    stage_id: int
    stage_name: str
    sequence: int
    assigned_role_id: Optional[int]
    assigned_role_name: Optional[str]
    assigned_employee_id: Optional[int]
    assigned_employee_name: Optional[str]
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    completed_quantity: int
    defect_quantity: int

class DealProductResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    quantity: int

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
    products: List[DealProductResponse]
    stages: List[DealProductStageResponse]
    logistics_status: str
    logistics_address: Optional[str]
    logistics_departure: Optional[datetime]
    logistics_arrival: Optional[datetime]
    logistics_route: Optional[str]

class ProductCreate(BaseModel):
    name: str
    default_stages: Optional[List[int]] = []

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    default_stages: Optional[List[int]] = None

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
    product_stages_map = {int(k): v for k, v in data.product_stages.items()}
    deal = await crud.create_deal(
        db=db,
        title=data.title,
        deal_type_id=data.deal_type_id,
        client_id=data.client_id,
        planned_date=data.planned_date,
        created_by=admin.id,
        products_data=[p.dict() for p in data.products],
        product_stages_map=product_stages_map
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

@router.post("/deals/{deal_id}/launch")
async def launch_deal(
    deal_id: int,
    admin: Employee = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    deal = await crud.get_deal_by_id(db, deal_id)
    if not deal:
        raise HTTPException(404, "Сделка не найдена")
    if deal.status != "draft":
        raise HTTPException(400, "Сделку можно запустить только из черновика")

    await crud.update_deal(db, deal_id, status="active", updated_by=admin.id)

    stages_stmt = select(DealProductStage).join(DealProduct).where(
        DealProduct.deal_id == deal_id,
        DealProductStage.assigned_role_id.isnot(None),
        DealProductStage.assigned_employee_id.is_(None),
        DealProductStage.status == "pending"
    )
    result = await db.execute(stages_stmt)
    stages = result.scalars().all()

    for stage in stages:
        employees = await crud.get_employees_with_role(db, stage.assigned_role_id, deal_id)
        if not employees:
            continue
        employee = employees[0]
        await crud.update_stage(db, stage.id, assigned_employee_id=employee.id)

        notif = Notification(
            employee_id=employee.id,
            admin_id=admin.id,
            type=NotificationType.COMMENDATION,
            message=f"Вам назначена задача: этап '{stage.stage.name}' в сделке '{deal.title}'",
            status=NotificationStatus.SENT,
            source="auto",
            deal_product_stage_id=stage.id,
            task_type="assignment"
        )
        db.add(notif)
        await db.commit()
        await notify_employee(employee.id)

    await notify_admin_clients()
    return {"status": "ok", "message": "Сделка запущена"}

@router.post("/deals/{deal_id}/cancel")
async def cancel_deal(
    deal_id: int,
    admin: Employee = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    await crud.update_deal(db, deal_id, status="cancelled", updated_by=admin.id)
    await notify_admin_clients()
    return {"status": "ok"}

@router.get("/my-tasks")
async def get_my_tasks(
    status: Optional[str] = None,
    employee: Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    tasks = await crud.get_employee_tasks(db, employee.id, status)
    return [
        {
            "id": t.id,
            "stage_name": t.stage.name,
            "deal_title": t.deal_product.deal.title,
            "product_name": t.deal_product.product.name,
            "quantity": t.deal_product.quantity,
            "completed_quantity": t.completed_quantity,
            "defect_quantity": t.defect_quantity,
            "status": t.status.value,
            "started_at": t.started_at,
            "completed_at": t.completed_at,
            "sequence": t.sequence
        }
        for t in tasks
    ]

@router.post("/tasks/{stage_id}/start")
async def start_task(
    stage_id: int,
    employee: Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    stage = await crud.get_stage_by_id(db, stage_id)
    if not stage:
        raise HTTPException(404, "Этап не найден")
    if stage.assigned_employee_id != employee.id:
        raise HTTPException(403, "Вы не назначены на этот этап")
    if stage.status != "pending":
        raise HTTPException(400, "Этап уже запущен или завершён")

    await crud.update_stage(db, stage_id, status="in_progress", started_at=datetime.now())
    return {"status": "ok", "started_at": stage.started_at}

@router.post("/tasks/{stage_id}/complete")
async def complete_task(
    stage_id: int,
    completed_quantity: int = Query(..., gt=0),
    defect_quantity: int = Query(0, ge=0),
    employee: Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    stage = await crud.get_stage_by_id(db, stage_id)
    if not stage:
        raise HTTPException(404, "Этап не найден")
    if stage.assigned_employee_id != employee.id:
        raise HTTPException(403, "Вы не назначены на этот этап")
    if stage.status != "in_progress":
        raise HTTPException(400, "Этап не в процессе выполнения")

    deal_product = stage.deal_product
    total_quantity = deal_product.quantity
    if completed_quantity > total_quantity:
        raise HTTPException(400, "Завершённое количество не может превышать общее")

    await crud.update_stage(
        db,
        stage_id,
        completed_quantity=completed_quantity,
        defect_quantity=defect_quantity,
        status="completed",
        completed_at=datetime.now()
    )

    if completed_quantity >= total_quantity:
        next_stage_stmt = select(DealProductStage).where(
            DealProductStage.deal_product_id == stage.deal_product_id,
            DealProductStage.sequence > stage.sequence
        ).order_by(DealProductStage.sequence).limit(1)
        result = await db.execute(next_stage_stmt)
        next_stage = result.scalar_one_or_none()
        if next_stage:
            if not next_stage.assigned_employee_id:
                employees = await crud.get_employees_with_role(db, next_stage.assigned_role_id, deal_product.deal_id)
                if employees:
                    emp = employees[0]
                    await crud.update_stage(db, next_stage.id, assigned_employee_id=emp.id)
                    notif = Notification(
                        employee_id=emp.id,
                        admin_id=employee.id,
                        type=NotificationType.COMMENDATION,
                        message=f"Новый этап '{next_stage.stage.name}' в сделке '{deal_product.deal.title}'",
                        status=NotificationStatus.SENT,
                        source="auto",
                        deal_product_stage_id=next_stage.id,
                        task_type="assignment"
                    )
                    db.add(notif)
                    await db.commit()
                    await notify_employee(emp.id)

    await db.commit()
    await notify_admin_clients()
    return {"status": "ok"}

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
    stages = []
    for dp in deal.deal_products:
        products.append({
            "id": dp.id,
            "product_id": dp.product_id,
            "product_name": dp.product.name,
            "quantity": dp.quantity
        })
        for st in dp.stages:
            stages.append({
                "id": st.id,
                "stage_id": st.stage_id,
                "stage_name": st.stage.name,
                "sequence": st.sequence,
                "assigned_role_id": st.assigned_role_id,
                "assigned_role_name": st.assigned_role.name if st.assigned_role else None,
                "assigned_employee_id": st.assigned_employee_id,
                "assigned_employee_name": st.assigned_employee.full_name if st.assigned_employee else None,
                "status": st.status.value,
                "started_at": st.started_at,
                "completed_at": st.completed_at,
                "completed_quantity": st.completed_quantity,
                "defect_quantity": st.defect_quantity
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
        stages=stages,
        logistics_status=deal.logistics_status.value,
        logistics_address=deal.logistics_address,
        logistics_departure=deal.logistics_departure,
        logistics_arrival=deal.logistics_arrival,
        logistics_route=deal.logistics_route
    )

# ==================== ТИПЫ ЗАДАЧ ====================

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

# ==================== ЗАДАЧИ ====================

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

# ==================== ПРОДУКТЫ ====================

@router.get("/products")
async def get_products(db: AsyncSession = Depends(get_db)):
    stmt = select(Product)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/products", status_code=201)
async def create_product(
    data: ProductCreate,
    db: AsyncSession = Depends(get_db)
):
    product = await crud.create_product(db, data.name, data.default_stages or [])
    return {
        "id": product.id,
        "name": product.name,
        "code": product.code,
        "default_stages": product.default_stages
    }

@router.put("/products/{product_id}")
async def update_product(
    product_id: int,
    data: ProductUpdate,
    db: AsyncSession = Depends(get_db)
):
    product = await crud.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    if data.name is not None:
        product.name = data.name
    if data.default_stages is not None:
        product.default_stages = data.default_stages
    await db.commit()
    await db.refresh(product)
    return {
        "id": product.id,
        "name": product.name,
        "code": product.code,
        "default_stages": product.default_stages
    }

@router.delete("/products/{product_id}", status_code=204)
async def delete_product(
    product_id: int,
    db: AsyncSession = Depends(get_db)
):
    product = await crud.get_product_by_id(db, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    await db.delete(product)
    await db.commit()
    return None

# ==================== ИП ====================
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

# ==================== МП ====================
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
    name: str   # например, "FBS"

class DealTypeUpdate(BaseModel):
    name: str

# --- Эндпоинты ---
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