from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel
from database import get_db
import crud
from models import Deal, Employee, TaskType, Task, DealType, TechCard, Role
from routers.auth import get_current_admin

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

class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    task_ids: Optional[List[int]] = None

class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    task_ids: Optional[List[int]] = None

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
            mp_id=data.mp_id
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
    return {
        "id": deal.id,
        "title": deal.title,
        "deal_type_id": deal.deal_type_id,
        "deal_type": deal.deal_type.name if deal.deal_type else None
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
            "employees": employees
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
        "tasks": tasks
    }


@router.post("/roles", status_code=201, response_model=RoleResponse)
async def create_role(data: RoleCreate, db: AsyncSession = Depends(get_db)):
    try:
        role = await crud.create_role(
            db,
            name=data.name,
            description=data.description,
            task_ids=data.task_ids
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
        "tasks": tasks
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
            task_ids=data.task_ids
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
        "tasks": tasks
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