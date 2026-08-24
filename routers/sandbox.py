from fastapi import APIRouter, Depends, HTTPException, Body, Request, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, cast, Integer, text
from typing import List, Optional, Dict
from pydantic import BaseModel
from database import get_db
import crud
from models import Deal, Employee, TaskType, Task, DealType, TechCard, Role, Notification, NotificationType, NotificationStatus, TaskExecution, TaskExecutionStatus, Explanation
from routers.auth import get_current_admin
import pandas as pd
import io
from schemas import DealProductItem
import os
import logging
router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])

# ==================== СХЕМЫ ====================
class DealTypeResponse(BaseModel):
    id: int
    name: str

class DealTypeCreate(BaseModel):
    name: str

class DealTypeUpdate(BaseModel):
    name: str

class DealCreate(BaseModel):
    title: str
    deal_type_id: int
    ip_id: Optional[int] = None
    mp_id: Optional[int] = None
    products: Optional[List[DealProductItem]] = None

class IPResponse(BaseModel):
    id: int
    name: str

class IPCreate(BaseModel):
    name: str

class IPUpdate(BaseModel):
    name: str

class MPResponse(BaseModel):
    id: int
    name: str

class MPCreate(BaseModel):
    name: str

class MPUpdate(BaseModel):
    name: str

class TechCardCreate(BaseModel):
    name: str
    task_ids: Optional[List[int]] = None

class TechCardUpdate(BaseModel):
    name: Optional[str] = None
    task_ids: Optional[List[int]] = None

class TechCardTaskResponse(BaseModel):
    id: int
    name: str
    sequence: int

class TechCardResponse(BaseModel):
    id: int
    name: str
    tasks: List[TechCardTaskResponse] = []

class ProductTypeCreate(BaseModel):
    name: str
    full_name: Optional[str] = None
    tech_card_id: Optional[int] = None

class ProductTypeUpdate(BaseModel):
    name: Optional[str] = None
    full_name: Optional[str] = None
    tech_card_id: Optional[int] = None

class ProductTypeResponse(BaseModel):
    id: int
    name: str
    full_name: Optional[str] = None
    tech_card_id: Optional[int]
    tech_card_name: Optional[str]

class RoleTaskResponse(BaseModel):
    id: int
    name: str

class EmployeeBrief(BaseModel):
    id: int
    full_name: str

class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    tasks: List[RoleTaskResponse] = []
    employees: List[EmployeeBrief] = []
    allow_multiple: bool = True

class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    task_ids: Optional[List[int]] = None
    allow_multiple: bool = True

class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    task_ids: Optional[List[int]] = None
    allow_multiple: Optional[bool] = None

class RoleEmployeeAdd(BaseModel):
    employee_id: int

# ==================== ЭНДПОИНТЫ ДЛЯ ТИПОВ СДЕЛОК ====================
@router.get("/deal-types", response_model=List[DealTypeResponse])
async def get_deal_types(db: AsyncSession = Depends(get_db)):
    return await crud.get_deal_types(db)

@router.post("/deal-types", status_code=201, response_model=DealTypeResponse)
async def create_deal_type(data: DealTypeCreate, db: AsyncSession = Depends(get_db)):
    try:
        deal_type = await crud.create_deal_type(db, data.name)
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    return deal_type

# ==================== ЭНДПОИНТЫ ДЛЯ ТИПОВ СДЕЛОК ====================
@router.get("/deal-types", response_model=List[DealTypeResponse])
async def get_deal_types(db: AsyncSession = Depends(get_db)):
    return await crud.get_deal_types(db)

@router.post("/deal-types", status_code=201, response_model=DealTypeResponse)
async def create_deal_type(data: DealTypeCreate, db: AsyncSession = Depends(get_db)):
    try:
        deal_type = await crud.create_deal_type(db, data.name)
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    return deal_type

# ---- СТАВИМ СПЕЦИФИЧНЫЕ ПУТИ РАНЬШЕ ДИНАМИЧЕСКИХ ----
@router.get("/deal-types/tasks")
async def get_deal_type_tasks(db: AsyncSession = Depends(get_db)):
    deal_types = await crud.get_deal_types(db)
    tasks = await crud.get_tasks(db)
    settings = await crud.get_deal_type_tasks(db)
    result = []
    for task in tasks:
        task_data = {"id": task.id, "name": task.name}
        for dt in deal_types:
            is_enabled = settings.get(dt.id, {}).get(task.id, True)
            task_data[f"type_{dt.id}"] = is_enabled
        result.append(task_data)
    return {"types": [{"id": dt.id, "name": dt.name} for dt in deal_types], "tasks": result}

from fastapi import Request
import logging

@router.put("/deal-types/tasks")
async def update_deal_type_tasks(request: Request, db: AsyncSession = Depends(get_db)):
    logging.info("=== ENTERED update_deal_type_tasks ===")
    try:
        data = await request.json()
        logging.info(f"PARSED JSON: {data}")
    except Exception as e:
        logging.error(f"Error reading JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    tasks_dict = data.get("tasks", data)
    converted = {}
    for key, value in tasks_dict.items():
        try:
            deal_type_id = int(key)
            task_ids = [int(x) for x in value]
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid data format")
        converted[deal_type_id] = task_ids

    await crud.set_deal_type_tasks(db, converted)
    return {"message": "Settings updated"}

@router.put("/deal-types/{type_id}", response_model=DealTypeResponse)
async def update_deal_type(type_id: int, data: DealTypeUpdate, db: AsyncSession = Depends(get_db)):
    try:
        deal_type = await crud.update_deal_type(db, type_id, data.name)
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    return deal_type

@router.delete("/deal-types/{type_id}", status_code=204)
async def delete_deal_type(type_id: int, db: AsyncSession = Depends(get_db)):
    await crud.delete_deal_type(db, type_id)
    return None

# ==================== ЭНДПОИНТЫ ДЛЯ СДЕЛОК ====================
@router.post("/deals", response_model=dict, status_code=201)
async def create_deal(data: DealCreate, db: AsyncSession = Depends(get_db)):
    try:
        deal = await crud.create_deal(
            db,
            title=data.title,
            deal_type_id=data.deal_type_id,
            ip_id=data.ip_id,
            mp_id=data.mp_id,
            products=data.products
        )
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    return {
        "id": deal.id,
        "title": deal.title,
        "deal_type_id": deal.deal_type_id,
        "ip_id": deal.ip_id,
        "mp_id": deal.mp_id
    }

@router.get("/deals", response_model=List[dict])
async def list_deals(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    deals = await crud.get_deals(db, skip, limit)
    return [
        {
            "id": d.id,
            "title": d.title,
            "deal_type_id": d.deal_type_id,
            "ip_id": d.ip_id,
            "ip_name": d.ip.name if d.ip else None,
            "mp_id": d.mp_id,
            "mp_name": d.mp.name if d.mp else None,
            "deal_type": d.deal_type.name if d.deal_type else None
        }
        for d in deals
    ]

@router.get("/deals/{deal_id}", response_model=dict)
async def get_deal(deal_id: int, db: AsyncSession = Depends(get_db)):
    deal = await crud.get_deal_by_id(db, deal_id)
    if not deal:
        raise HTTPException(404, "Deal not found")
    products = []
    for dp in deal.deal_products:
        if dp.product_type:
            products.append({
                "name": dp.product_type.name,
                "full_name": dp.product_type.full_name,
                "quantity": dp.quantity
            })

    # ---- Получение задач и их выполнения ----
    # Используем сырой SQL для извлечения значений из JSON
    from sqlalchemy import text
    stmt = text("""
        SELECT 
            n.id as notif_id,
            n.extra_data,
            te.status as exec_status,
            te.started_at,
            te.completed_at,
            e.full_name,
            t.id as task_id,
            t.name as task_name
        FROM notifications n
        LEFT JOIN task_executions te ON te.notification_id = n.id
        JOIN employees e ON e.id = n.employee_id
        JOIN tasks t ON t.id = (n.extra_data->>'task_id')::integer
        WHERE n.type = 'task_assignment'
            AND n.status = 'sent'
            AND (n.extra_data->>'deal_id')::integer = :deal_id
        ORDER BY t.name, e.full_name
    """)
    result = await db.execute(stmt, {"deal_id": deal_id})
    rows = result.fetchall()

    tasks_dict = {}
    for row in rows:
        task_id = row.task_id
        if task_id not in tasks_dict:
            tasks_dict[task_id] = {
                "task_id": task_id,
                "task_name": row.task_name,
                "assignees": []
            }
        status_value = row.exec_status if row.exec_status else "not_started"
        started_at = row.started_at.isoformat() if row.started_at else None
        completed_at = row.completed_at.isoformat() if row.completed_at else None
        tasks_dict[task_id]["assignees"].append({
            "employee_name": row.full_name,
            "status": status_value,
            "started_at": started_at,
            "completed_at": completed_at
        })

    tasks_list = list(tasks_dict.values())

    return {
        "id": deal.id,
        "title": deal.title,
        "deal_type_id": deal.deal_type_id,
        "deal_type": deal.deal_type.name if deal.deal_type else None,
        "products": products,
        "tasks": tasks_list
    }

@router.delete("/deals/{deal_id}", status_code=204)
async def delete_deal(
    deal_id: int,
    admin: Employee = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    await crud.delete_deal(db, deal_id)
    return None

# ==================== ЭНДПОИНТЫ ДЛЯ ИП ====================
@router.get("/ips", response_model=List[IPResponse])
async def get_ips(db: AsyncSession = Depends(get_db)):
    ips = await crud.get_all_ips(db)
    return [{"id": i.id, "name": i.name} for i in ips]

@router.post("/ips", status_code=201, response_model=IPResponse)
async def create_ip(data: IPCreate, db: AsyncSession = Depends(get_db)):
    ip = await crud.create_ip(db, data.name)
    return {"id": ip.id, "name": ip.name}

@router.put("/ips/{ip_id}", response_model=IPResponse)
async def update_ip(ip_id: int, data: IPUpdate, db: AsyncSession = Depends(get_db)):
    try:
        ip = await crud.update_ip(db, ip_id, data.name)
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    return {"id": ip.id, "name": ip.name}

@router.delete("/ips/{ip_id}", status_code=204)
async def delete_ip(ip_id: int, db: AsyncSession = Depends(get_db)):
    await crud.delete_ip(db, ip_id)
    return None

# ==================== ЭНДПОИНТЫ ДЛЯ МП ====================
@router.get("/mps", response_model=List[MPResponse])
async def get_mps(db: AsyncSession = Depends(get_db)):
    mps = await crud.get_all_mps(db)
    return [{"id": m.id, "name": m.name} for m in mps]

@router.post("/mps", status_code=201, response_model=MPResponse)
async def create_mp(data: MPCreate, db: AsyncSession = Depends(get_db)):
    try:
        mp = await crud.create_mp(db, data.name)
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    return {"id": mp.id, "name": mp.name}

@router.put("/mps/{mp_id}", response_model=MPResponse)
async def update_mp(mp_id: int, data: MPUpdate, db: AsyncSession = Depends(get_db)):
    try:
        mp = await crud.update_mp(db, mp_id, data.name)
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    return {"id": mp.id, "name": mp.name}

@router.delete("/mps/{mp_id}", status_code=204)
async def delete_mp(mp_id: int, db: AsyncSession = Depends(get_db)):
    await crud.delete_mp(db, mp_id)
    return None

# ==================== ЭНДПОИНТЫ ДЛЯ ТИПОВ ЗАДАЧ ====================
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

@router.put("/task-types/{type_id}", response_model=dict)
async def update_task_type(
    type_id: int,
    data: DealTypeUpdate,  # можно переиспользовать схему с name
    db: AsyncSession = Depends(get_db)
):
    try:
        task_type = await crud.update_task_type(db, type_id, data.name)
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    return {"id": task_type.id, "name": task_type.name}

@router.put("/tasks/{task_id}", response_model=dict)
async def update_task(
    task_id: int,
    name: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db)
):
    try:
        task = await crud.update_task(db, task_id, name=name)
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    return {"id": task.id, "name": task.name, "task_type_id": task.task_type_id}

@router.delete("/task-types/{type_id}", status_code=204)
async def delete_task_type(
    type_id: int,
    db: AsyncSession = Depends(get_db)
):
    await crud.delete_task_type(db, type_id)
    return None

# ==================== ЭНДПОИНТЫ ДЛЯ ЗАДАЧ ====================
@router.get("/tasks", response_model=List[dict])
async def get_tasks(db: AsyncSession = Depends(get_db)):
    tasks = await crud.get_tasks(db)
    return [
        {
            "id": t.id,
            "name": t.name,
            "task_type_id": t.task_type_id,
            "task_type_name": t.task_type.name if t.task_type else None
        }
        for t in tasks
    ]

@router.post("/tasks", status_code=201, response_model=dict)
async def create_task(
    name: str = Body(...),
    task_type_id: Optional[int] = Body(None),
    db: AsyncSession = Depends(get_db)
):
    task = await crud.create_task(db, name, task_type_id)
    return {"id": task.id, "name": task.name, "task_type_id": task.task_type_id}

@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(
    task_id: int,
    db: AsyncSession = Depends(get_db)
):
    await crud.delete_task(db, task_id)
    return None

# ==================== ЭНДПОИНТЫ ДЛЯ ТЕХКАРТ ====================
@router.get("/tech-cards", response_model=List[TechCardResponse])
async def get_tech_cards(db: AsyncSession = Depends(get_db)):
    tech_cards = await crud.get_tech_cards(db)
    result = []
    for tc in tech_cards:
        tasks = [
            {"id": tct.task.id, "name": tct.task.name, "sequence": tct.sequence}
            for tct in tc.tech_card_tasks
            if tct.task is not None
        ]
        result.append({"id": tc.id, "name": tc.name, "tasks": tasks})
    return result

@router.post("/tech-cards", status_code=201, response_model=TechCardResponse)
async def create_tech_card(data: TechCardCreate, db: AsyncSession = Depends(get_db)):
    tech_card = await crud.create_tech_card(db, data.name)
    if data.task_ids:
        await crud.reorder_tech_card_tasks(db, tech_card.id, data.task_ids)
        tech_card = await crud.get_tech_card(db, tech_card.id)
    tech_card = await crud.get_tech_card(db, tech_card.id)
    tasks = [
        {"id": tct.task.id, "name": tct.task.name, "sequence": tct.sequence}
        for tct in tech_card.tech_card_tasks
        if tct.task is not None
    ]
    return {"id": tech_card.id, "name": tech_card.name, "tasks": tasks}

@router.delete("/tech-cards/{tech_card_id}", status_code=204)
async def delete_tech_card(tech_card_id: int, db: AsyncSession = Depends(get_db)):
    await crud.delete_tech_card(db, tech_card_id)
    return None

@router.put("/tech-cards/{tech_card_id}", response_model=TechCardResponse)
async def update_tech_card(
    tech_card_id: int,
    data: TechCardUpdate,
    db: AsyncSession = Depends(get_db)
):
    # Обновляем название, если передано
    if data.name is not None:
        await crud.update_tech_card(db, tech_card_id, data.name)
    # Если передан список задач – перестраиваем порядок
    if data.task_ids is not None:
        await crud.reorder_tech_card_tasks(db, tech_card_id, data.task_ids)
    # Получаем обновлённую техкарту
    tech_card = await crud.get_tech_card(db, tech_card_id)
    if not tech_card:
        raise HTTPException(404, "Tech card not found")
    tasks = [
        {"id": tct.task.id, "name": tct.task.name, "sequence": tct.sequence}
        for tct in tech_card.tech_card_tasks
        if tct.task is not None
    ]
    return {"id": tech_card.id, "name": tech_card.name, "tasks": tasks}

@router.get("/tech-cards/{tech_card_id}", response_model=TechCardResponse)
async def get_tech_card(tech_card_id: int, db: AsyncSession = Depends(get_db)):
    tech_card = await crud.get_tech_card(db, tech_card_id)
    if not tech_card:
        raise HTTPException(404, "Tech card not found")
    tasks = [
        {"id": tct.task.id, "name": tct.task.name, "sequence": tct.sequence}
        for tct in tech_card.tech_card_tasks
        if tct.task is not None
    ]
    return {"id": tech_card.id, "name": tech_card.name, "tasks": tasks}

@router.get("/product-types", response_model=List[ProductTypeResponse])
async def get_product_types(db: AsyncSession = Depends(get_db)):
    products = await crud.get_product_types(db)
    return [
        {
            "id": p.id,
            "name": p.name,
            "full_name": p.full_name,
            "tech_card_id": p.tech_card_id,
            "tech_card_name": p.tech_card.name if p.tech_card else None
        }
        for p in products
    ]

@router.get("/product-types/{product_id}", response_model=ProductTypeResponse)
async def get_product_type(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await crud.get_product_type(db, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    return {
        "id": product.id,
        "name": product.name,
        "tech_card_id": product.tech_card_id,
        "tech_card_name": product.tech_card.name if product.tech_card else None
    }

@router.post("/product-types", status_code=201, response_model=ProductTypeResponse)
async def create_product_type(
    data: ProductTypeCreate,
    db: AsyncSession = Depends(get_db)
):
    try:
        product = await crud.create_product_type(
            db,
            name=data.name,
            full_name=data.full_name,
            tech_card_id=data.tech_card_id
        )
        product = await crud.get_product_type(db, product.id)
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    return {
        "id": product.id,
        "name": product.name,
        "full_name": product.full_name,
        "tech_card_id": product.tech_card_id,
        "tech_card_name": product.tech_card.name if product.tech_card else None
    }

@router.put("/product-types/{product_id}", response_model=ProductTypeResponse)
async def update_product_type(
    product_id: int,
    data: ProductTypeUpdate,
    db: AsyncSession = Depends(get_db)
):
    try:
        product = await crud.update_product_type(
            db,
            product_id,
            name=data.name,
            full_name=data.full_name,
            tech_card_id=data.tech_card_id
        )
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    return {
        "id": product.id,
        "name": product.name,
        "full_name": product.full_name,
        "tech_card_id": product.tech_card_id,
        "tech_card_name": product.tech_card.name if product.tech_card else None
    }

@router.delete("/product-types/{product_id}", status_code=204)
async def delete_product_type(product_id: int, db: AsyncSession = Depends(get_db)):
    await crud.delete_product_type(db, product_id)
    return None

# ==================== ЭНДПОИНТЫ ДЛЯ РОЛЕЙ ====================

@router.get("/roles", response_model=List[RoleResponse])
async def get_roles(db: AsyncSession = Depends(get_db)):
    roles = await crud.get_roles(db)
    result = []
    for role in roles:
        tasks = [{"id": rt.task.id, "name": rt.task.name} for rt in role.role_tasks if rt.task]
        employees = [{"id": er.employee.id, "full_name": er.employee.full_name} for er in role.employee_roles if er.employee]
        result.append({
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "tasks": tasks,
            "employees": employees,
            "allow_multiple": role.allow_multiple   # добавлено
        })
    return result

@router.get("/roles/{role_id}", response_model=RoleResponse)
async def get_role(role_id: int, db: AsyncSession = Depends(get_db)):
    role = await crud.get_role(db, role_id)
    if not role:
        raise HTTPException(404, "Role not found")
    tasks = [
        {"id": rt.task.id, "name": rt.task.name}
        for rt in role.role_tasks
        if rt.task is not None
    ]
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "tasks": tasks,
        "allow_multiple": role.allow_multiple   # добавлено
    }


@router.post("/roles", status_code=201, response_model=RoleResponse)
async def create_role(data: RoleCreate, db: AsyncSession = Depends(get_db)):
    try:
        role = await crud.create_role(
            db,
            name=data.name,
            description=data.description,
            task_ids=data.task_ids,
            allow_multiple=data.allow_multiple
        )
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    # Перезагружаем роль, чтобы подгрузить задачи
    role = await crud.get_role(db, role.id)
    tasks = [
        {"id": rt.task.id, "name": rt.task.name}
        for rt in role.role_tasks
        if rt.task is not None
    ]
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "tasks": tasks,
        "allow_multiple": role.allow_multiple   # добавлено
    }


@router.put("/roles/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    data: RoleUpdate,
    db: AsyncSession = Depends(get_db)
):
    try:
        role = await crud.update_role(
            db,
            role_id,
            name=data.name,
            description=data.description,
            task_ids=data.task_ids,
            allow_multiple=data.allow_multiple
        )
    except ValueError as e:
        raise HTTPException(404, detail=str(e))
    except Exception as e:
        raise HTTPException(400, detail=str(e))
    # Перезагружаем роль, чтобы подгрузить задачи
    role = await crud.get_role(db, role_id)
    tasks = [
        {"id": rt.task.id, "name": rt.task.name}
        for rt in role.role_tasks
        if rt.task is not None
    ]
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "tasks": tasks,
        "allow_multiple": role.allow_multiple   # добавлено
    }


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(role_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await crud.delete_role(db, role_id)
    except ValueError as e:
        raise HTTPException(404, detail=str(e))
    return None

# ==================== НАЗНАЧЕНИЕ СОТРУДНИКОВ НА РОЛИ ====================

@router.post("/roles/{role_id}/employees", status_code=201, response_model=EmployeeBrief)
async def add_employee_to_role(
    role_id: int,
    data: RoleEmployeeAdd,
    db: AsyncSession = Depends(get_db)
):
    try:
        link = await crud.add_employee_to_role(db, role_id, data.employee_id)
        # Возвращаем данные сотрудника
        employee = await crud.get_employee_by_id(db, data.employee_id)
        if not employee:
            raise HTTPException(404, "Employee not found")
        return {"id": employee.id, "full_name": employee.full_name}
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    except Exception as e:
        raise HTTPException(400, detail=str(e))


@router.delete("/roles/{role_id}/employees/{employee_id}", status_code=204)
async def remove_employee_from_role(
    role_id: int,
    employee_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        await crud.remove_employee_from_role(db, role_id, employee_id)
    except ValueError as e:
        raise HTTPException(404, detail=str(e))
    return None

@router.get("/employees/{employee_id}/roles", response_model=List[dict])
async def get_employee_roles(
    employee_id: int,
    db: AsyncSession = Depends(get_db)
):
    employee = await crud.get_employee_by_id(db, employee_id)
    if not employee:
        raise HTTPException(404, "Employee not found")
    roles = await crud.get_roles_for_employee(db, employee_id)
    # Возвращаем только id и name
    return [{"id": r.id, "name": r.name} for r in roles]

@router.post("/roles/{role_id}/tasks", status_code=201)
async def add_task_to_role(
    role_id: int,
    task_id: int = Body(..., embed=True),
    db: AsyncSession = Depends(get_db)
):
    try:
        await crud.add_task_to_role(db, role_id, task_id)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    return {"message": "Task added to role"}

@router.delete("/roles/{role_id}/tasks/{task_id}", status_code=204)
async def remove_task_from_role(
    role_id: int,
    task_id: int,
    db: AsyncSession = Depends(get_db)
):
    try:
        await crud.remove_task_from_role(db, role_id, task_id)
    except ValueError as e:
        raise HTTPException(404, detail=str(e))
    return None



@router.post("/import/preview")
async def preview_import(file: UploadFile = File(...)):
    """Прочитать Excel‑файл и вернуть список товаров для предпросмотра."""
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(400, detail="Файл должен быть Excel (.xlsx или .xls)")

    try:
        contents = await file.read()
        df = pd.read_excel(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(400, detail=f"Не удалось прочитать файл: {str(e)}")

    if df.empty:
        raise HTTPException(400, detail="Файл пуст")

    # Пытаемся найти колонки по имени
    columns = df.columns.tolist()
    name_col = None
    full_name_col = None
    quantity_col = None

    for col in columns:
        col_lower = col.lower().strip()
        if col_lower in ('наименование', 'name', 'товар', 'артикул'):
            name_col = col
        elif col_lower in ('полное наименование', 'full_name', 'описание'):
            full_name_col = col
        elif col_lower in ('количество', 'quantity', 'кол-во', 'qty'):
            quantity_col = col

    # Если не нашли по имени – берём первые три колонки по порядку
    if name_col is None and len(columns) > 0:
        name_col = columns[0]
    if full_name_col is None and len(columns) > 1:
        full_name_col = columns[1]
    if quantity_col is None and len(columns) > 2:
        quantity_col = columns[2]

    result = []
    for _, row in df.iterrows():
        name = str(row[name_col]) if name_col in row else ''
        full_name = str(row[full_name_col]) if full_name_col in row else ''
        quantity = 1
        if quantity_col and quantity_col in row:
            try:
                quantity = int(row[quantity_col])
            except (ValueError, TypeError):
                quantity = 1
        # Пропускаем пустые названия
        if name and name.strip():
            result.append({
                "name": name.strip(),
                "full_name": full_name.strip() if full_name else None,
                "quantity": quantity
            })

    return {"products": result}

from datetime import datetime
import os

@router.get("/import/auto")
async def auto_import(
    deal_type: str,
    ip_name: Optional[str] = None,
    mp_name: Optional[str] = None,
    date: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    # Если дата не передана, берём сегодня в формате YYMMDD
    if not date:
        date = datetime.now().strftime("%y%m%d")  # например 260820
    
    base_path = r"w:\!МП_(FSk)"
    
    if deal_type == "FBS":
        file_path = os.path.join(base_path, "!FBS", f"{date}_FBS", "Книга1.xlsx")
    elif deal_type == "FSK":
        file_path = os.path.join(base_path, f"{date}_FSk", "b24.xlsx")
    elif deal_type == "FBO":
        if not ip_name or not mp_name:
            raise HTTPException(400, "Для FBO необходимо указать ИП и МП")
        folder = f"{date}_{ip_name}_{mp_name}"
        file_path = os.path.join(base_path, folder, "b24.xlsx")
    else:
        raise HTTPException(400, f"Неизвестный тип сделки: {deal_type}")

    if not os.path.exists(file_path):
        raise HTTPException(404, f"Файл не найден: {file_path}")

    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        raise HTTPException(400, f"Ошибка чтения файла: {str(e)}")

    if df.empty:
        raise HTTPException(400, "Файл пуст")

    # Определяем колонки (та же логика, что в preview_import)
    columns = df.columns.tolist()
    name_col = None
    full_name_col = None
    quantity_col = None
    for col in columns:
        col_lower = col.lower().strip()
        if col_lower in ('наименование', 'name', 'товар', 'артикул'):
            name_col = col
        elif col_lower in ('полное наименование', 'full_name', 'описание'):
            full_name_col = col
        elif col_lower in ('количество', 'quantity', 'кол-во', 'qty'):
            quantity_col = col

    if name_col is None and len(columns) > 0:
        name_col = columns[0]
    if full_name_col is None and len(columns) > 1:
        full_name_col = columns[1]
    if quantity_col is None and len(columns) > 2:
        quantity_col = columns[2]

    result = []
    for _, row in df.iterrows():
        name = str(row[name_col]) if name_col in row else ''
        full_name = str(row[full_name_col]) if full_name_col in row else ''
        quantity = 1
        if quantity_col and quantity_col in row:
            try:
                quantity = int(row[quantity_col])
            except:
                quantity = 1
        if name and name.strip():
            result.append({
                "name": name.strip(),
                "full_name": full_name.strip() if full_name else None,
                "quantity": quantity
            })

    return {"products": result}

class ImportPathRequest(BaseModel):
    path: str

@router.post("/import/by-path")
async def import_by_path(data: ImportPathRequest, db: AsyncSession = Depends(get_db)):
    file_path = data.path
    if not os.path.exists(file_path):
        raise HTTPException(404, f"Файл не найден: {file_path}")

    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        raise HTTPException(400, f"Ошибка чтения файла: {str(e)}")

    if df.empty:
        raise HTTPException(400, "Файл пуст")

    # Определение колонок (та же логика, что в preview_import)
    columns = df.columns.tolist()
    name_col = None
    full_name_col = None
    quantity_col = None
    for col in columns:
        col_lower = col.lower().strip()
        if col_lower in ('наименование', 'name', 'товар', 'артикул'):
            name_col = col
        elif col_lower in ('полное наименование', 'full_name', 'описание'):
            full_name_col = col
        elif col_lower in ('количество', 'quantity', 'кол-во', 'qty'):
            quantity_col = col

    if name_col is None and len(columns) > 0:
        name_col = columns[0]
    if full_name_col is None and len(columns) > 1:
        full_name_col = columns[1]
    if quantity_col is None and len(columns) > 2:
        quantity_col = columns[2]

    result = []
    for _, row in df.iterrows():
        name = str(row[name_col]) if name_col in row else ''
        full_name = str(row[full_name_col]) if full_name_col in row else ''
        quantity = 1
        if quantity_col and quantity_col in row:
            try:
                quantity = int(row[quantity_col])
            except:
                quantity = 1
        if name and name.strip():
            result.append({
                "name": name.strip(),
                "full_name": full_name.strip() if full_name else None,
                "quantity": quantity
            })

    return {"products": result}

@router.post("/deals/{deal_id}/start")
async def start_deal(
    deal_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: Employee = Depends(get_current_admin)
):
    # 1. Загружаем сделку со всеми зависимостями
    deal = await crud.get_deal_with_products_and_tech_cards(db, deal_id)
    if not deal:
        raise HTTPException(404, "Сделка не найдена")

    # 2. Собираем словарь: task_id -> список товаров с количеством
    task_products = {}  # {task_id: [{'name': product_name, 'quantity': qty}, ...]}
    for dp in deal.deal_products:
        product_type = dp.product_type
        if not product_type or not product_type.tech_card:
            continue
        tech_card = product_type.tech_card
        # Получаем задачи техкарты в порядке sequence
        tasks = sorted(tech_card.tech_card_tasks, key=lambda x: x.sequence)
        for tct in tasks:
            task = tct.task
            if not task:
                continue
            task_id = task.id
            task_products.setdefault(task_id, []).append({
                "name": product_type.name,
                "full_name": product_type.full_name or product_type.name,
                "quantity": dp.quantity
            })

    if not task_products:
        raise HTTPException(400, "Нет товаров с техкартами")

    # 3. Получаем роли для всех задач
    task_ids = list(task_products.keys())
    task_roles = await crud.get_task_roles(db, task_ids)

    # 4. Собираем всех сотрудников, которым нужно отправить уведомления
    # Словарь: (employee_id, task_id) -> список товаров
    notifications_data = {}  # ключ: (emp_id, task_id), значение: list of products
    for task_id, products in task_products.items():
        role_ids = task_roles.get(task_id, [])
        if not role_ids:
            continue
        # Получаем сотрудников для этих ролей
        role_employees = await crud.get_employees_for_roles(db, role_ids)
        # Для каждого сотрудника добавляем задачу и товары
        employees = set()
        for role_id in role_ids:
            employees.update(role_employees.get(role_id, []))
        for emp_id in employees:
            key = (emp_id, task_id)
            if key not in notifications_data:
                notifications_data[key] = []
            notifications_data[key].extend(products)  # добавляем товары для этой задачи

    if not notifications_data:
        raise HTTPException(400, "Нет сотрудников, назначенных на задачи")

    # 5. Формируем и сохраняем уведомления
    from models import Notification, NotificationStatus
    from sse import notify_employee

    created_count = 0
    for (emp_id, task_id), products in notifications_data.items():
        # Находим задачу (первый попавшийся продукт даст имя задачи)
        # Но лучше получить имя задачи из БД
        task = await crud.get_task(db, task_id)
        if not task:
            continue
        # Группируем товары по имени (суммируем количества)
        product_quantities = {}
        for p in products:
            key = p['full_name']  # или p['name']
            if key not in product_quantities:
                product_quantities[key] = 0
            product_quantities[key] += p['quantity']
        # Формируем текст
        items_text = ", ".join([f"{name} — {qty} шт." for name, qty in product_quantities.items()])
        message = f"📋 Задача: {task.name}\nТовары: {items_text}"

        notification = Notification(
            employee_id=emp_id,
            admin_id=admin.id,
            type=NotificationType.TASK_ASSIGNMENT,
            message=message,
            status=NotificationStatus.SENT,
            source="admin",
            extra_data={
                "deal_id": deal_id,
                "task_id": task_id,
                "deal_title": deal.title,
                "task_name": task.name,
                "products": [
                    {"name": p['full_name'], "quantity": p['quantity']}
                    for p in products
                ]
            }
        )
        db.add(notification)
        await db.flush()
        task_exec = TaskExecution(
            notification_id=notification.id,
            employee_id=emp_id,
            status=TaskExecutionStatus.NOT_STARTED
        )
        db.add(task_exec)
        created_count += 1

    await db.commit()

    # 6. Уведомляем сотрудников через SSE (опционально)
    for (emp_id, _), _ in notifications_data.items():
        await notify_employee(emp_id)

    return {"message": f"Сделка запущена, отправлено {created_count} уведомлений"}

@router.get("/mailing/notifications")
async def get_mailing_notifications(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    stmt = text("""
        SELECT 
            n.id,
            n.extra_data,
            n.message,
            n.created_at,
            te.status AS exec_status,
            te.started_at,
            te.completed_at,
            e.full_name AS employee_name,
            t.name AS task_name,
            d.title AS deal_title
        FROM notifications n
        LEFT JOIN task_executions te ON te.notification_id = n.id
        JOIN employees e ON e.id = n.employee_id
        JOIN tasks t ON t.id = (n.extra_data->>'task_id')::integer
        JOIN deals d ON d.id = (n.extra_data->>'deal_id')::integer
        WHERE n.type = 'task_assignment'
            AND n.status = 'sent'
        ORDER BY n.created_at DESC
        OFFSET :skip LIMIT :limit
    """)
    result = await db.execute(stmt, {"skip": skip, "limit": limit})
    rows = result.fetchall()

    output = []
    for row in rows:
        output.append({
            "id": row.id,
            "employee_name": row.employee_name,
            "task_name": row.task_name,
            "deal_title": row.deal_title,
            "message": row.message,
            "extra_data": row.extra_data,  # JSON
            "execution_status": row.exec_status if row.exec_status else "not_started",
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        })
    return output

@router.delete("/mailing/notifications/{notification_id}")
async def delete_mailing_notification(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    admin: Employee = Depends(get_current_admin)
):
    # Проверяем, что уведомление существует и имеет тип TASK_ASSIGNMENT
    stmt = select(Notification).where(
        Notification.id == notification_id,
        Notification.type == NotificationType.TASK_ASSIGNMENT
    )
    result = await db.execute(stmt)
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(404, detail="Уведомление не найдено или не относится к рассылке")
    
    # Удаляем связанную TaskExecution, если есть
    te_stmt = select(TaskExecution).where(TaskExecution.notification_id == notification_id)
    te_result = await db.execute(te_stmt)
    task_exec = te_result.scalar_one_or_none()
    if task_exec:
        await db.delete(task_exec)
    
    # Удаляем объяснительную, если есть
    exp_stmt = select(Explanation).where(Explanation.notification_id == notification_id)
    exp_result = await db.execute(exp_stmt)
    explanation = exp_result.scalar_one_or_none()
    if explanation:
        await db.delete(explanation)
    
    await db.delete(notification)
    await db.commit()
    return {"message": "Уведомление удалено"}