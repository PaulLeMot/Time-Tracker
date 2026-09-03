from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from database import get_db
from routers.auth import get_current_employee
import models
from models import Notification, Explanation, NotificationStatus, NotificationType, TaskBreak
from sse import notify_admin_clients
from models import TaskExecution, TaskExecutionStatus
from crud import get_task_execution_by_notification, update_task_execution_status
from fastapi import Body
from sqlalchemy import select, delete
from models import Notification, NotificationType, NotificationStatus, TaskExecution, TaskExecutionStatus, Explanation
from sse import notify_employee
import crud

router = APIRouter(prefix="/api/employee", tags=["employee"])

class NotificationResponse(BaseModel):
    id: int
    type: str
    message: str
    created_at: datetime
    has_explanation: bool
    explanation_text: Optional[str] = None
    extra_data: Optional[dict] = None

class ExplanationCreate(BaseModel):
    explanation_text: str

class ExplanationResponse(BaseModel):
    id: int
    notification_id: int
    employee_id: int
    explanation_text: str
    created_at: datetime

@router.get("/notifications", response_model=List[NotificationResponse])
async def get_employee_notifications(
    employee: models.Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db),
    type: Optional[str] = None
):
    conditions = [
        Notification.employee_id == employee.id,
        Notification.status == NotificationStatus.SENT
    ]
    
    if type is None:
        # Если тип не указан – исключаем уведомления о задачах
        conditions.append(Notification.type != NotificationType.TASK_ASSIGNMENT)
    else:
        # Если тип указан – фильтруем по нему
        try:
            notif_type = NotificationType(type)
            conditions.append(Notification.type == notif_type)
        except ValueError:
            raise HTTPException(400, "Invalid notification type")

    stmt = (
        select(Notification, Explanation.explanation_text)
        .outerjoin(Explanation, Explanation.notification_id == Notification.id)
        .where(*conditions)
        .order_by(Notification.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    response = []
    for notif, explanation_text in rows:
        response.append(NotificationResponse(
            id=notif.id,
            type=notif.type.value,
            message=notif.message,
            created_at=notif.created_at,
            has_explanation=explanation_text is not None,
            explanation_text=explanation_text,
            extra_data=notif.extra_data
        ))
    return response

@router.post("/notifications/{notification_id}/explanation", response_model=dict)
async def create_explanation(
    notification_id: int,
    data: ExplanationCreate,
    employee: models.Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Notification).where(Notification.id == notification_id)
    result = await db.execute(stmt)
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Notification not found")
    if notif.employee_id != employee.id:
        raise HTTPException(403, "You are not allowed to explain this notification")
    if notif.status != NotificationStatus.SENT:
        raise HTTPException(400, "Only sent notifications can be explained")
    
    exp_stmt = select(Explanation).where(Explanation.notification_id == notification_id)
    exp_result = await db.execute(exp_stmt)
    if exp_result.scalar_one_or_none():
        raise HTTPException(400, "Explanation already submitted")
    
    explanation = Explanation(
        notification_id=notification_id,
        employee_id=employee.id,
        explanation_text=data.explanation_text
    )
    db.add(explanation)
    await db.commit()
    return {"message": "Explanation submitted successfully"}

@router.get("/notifications/{notification_id}/explanation", response_model=ExplanationResponse)
async def get_explanation(
    notification_id: int,
    employee: models.Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Explanation).where(Explanation.notification_id == notification_id)
    result = await db.execute(stmt)
    explanation = result.scalar_one_or_none()
    if not explanation:
        raise HTTPException(404, "Explanation not found")
    if explanation.employee_id != employee.id:
        raise HTTPException(403, "Not your explanation")
    return ExplanationResponse(
        id=explanation.id,
        notification_id=explanation.notification_id,
        employee_id=explanation.employee_id,
        explanation_text=explanation.explanation_text,
        created_at=explanation.created_at
    )

class ProposedTimeRequest(BaseModel):
    proposed_end_time: datetime

@router.post("/notifications/{notification_id}/propose-end-time")
async def propose_end_time(
    notification_id: int,
    data: ProposedTimeRequest,
    employee: models.Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    # 1. Проверяем существование уведомления и его принадлежность сотруднику
    stmt = select(Notification).where(Notification.id == notification_id)
    result = await db.execute(stmt)
    notif = result.scalar_one_or_none()
    if not notif or notif.employee_id != employee.id:
        raise HTTPException(404, "Уведомление не найдено")

    # 2. Проверяем, что это именно уведомление о незавершённом дне
    if notif.type != NotificationType.WARNING or notif.message != "Не был завершен рабочий день":
        raise HTTPException(400, "Недопустимый тип уведомления")

    # 3. Сохраняем предложенное время в extra_data
    current_extra = dict(notif.extra_data) if notif.extra_data else {}
    current_extra["proposed_end_time"] = data.proposed_end_time.isoformat()
    notif.extra_data = current_extra   # ← принудительное обновление
    notif.status = NotificationStatus.DRAFT

    # 4. Создаём или обновляем объяснительную, чтобы уведомление считалось "отвеченным"
    explanation_text = f"Предложено время завершения: {data.proposed_end_time.strftime('%d.%m.%Y %H:%M')}"
    exp_stmt = select(Explanation).where(Explanation.notification_id == notification_id)
    exp_result = await db.execute(exp_stmt)
    explanation = exp_result.scalar_one_or_none()

    if explanation:
        explanation.explanation_text = explanation_text
        explanation.created_at = datetime.now()
    else:
        explanation = Explanation(
            notification_id=notification_id,
            employee_id=employee.id,
            explanation_text=explanation_text
        )
        db.add(explanation)

    await db.commit()

    # 5. Оповещаем админов
    await notify_admin_clients()

    return {"message": "Предложение отправлено администратору"}

@router.post("/tasks/{notification_id}/start")
async def start_task(
    notification_id: int,
    employee: models.Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    # 1. Проверяем, что уведомление существует, принадлежит сотруднику и это task_assignment
    stmt = select(Notification).where(Notification.id == notification_id)
    result = await db.execute(stmt)
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Уведомление не найдено")
    if notif.employee_id != employee.id:
        raise HTTPException(403, "Это не ваше уведомление")
    if notif.type != NotificationType.TASK_ASSIGNMENT:
        raise HTTPException(400, "Это уведомление не является задачей")

    # 2. Получаем запись выполнения
    task_exec = await get_task_execution_by_notification(db, notification_id)
    if not task_exec:
        # Создаём, если вдруг нет (на случай, если не создалось автоматически)
        task_exec = TaskExecution(
            notification_id=notification_id,
            employee_id=employee.id,
            status=TaskExecutionStatus.NOT_STARTED
        )
        db.add(task_exec)
        await db.flush()

    # 3. Проверяем, не начата ли уже задача
    if task_exec.status == TaskExecutionStatus.IN_PROGRESS:
        raise HTTPException(400, "Задача уже начата")
    if task_exec.status == TaskExecutionStatus.COMPLETED:
        raise HTTPException(400, "Задача уже завершена")

    # 4. Обновляем статус и время начала
    task_exec.status = TaskExecutionStatus.IN_PROGRESS
    task_exec.started_at = datetime.now()
    await db.commit()

    return {"message": "Задача начата", "started_at": task_exec.started_at.isoformat()}


@router.post("/tasks/{notification_id}/complete")
async def complete_task(
    notification_id: int,
    employee: models.Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    # 1. Проверяем уведомление
    stmt = select(Notification).where(Notification.id == notification_id)
    result = await db.execute(stmt)
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Уведомление не найдено")
    if notif.employee_id != employee.id:
        raise HTTPException(403, "Это не ваше уведомление")
    if notif.type != NotificationType.TASK_ASSIGNMENT:
        raise HTTPException(400, "Это уведомление не является задачей")

    # 2. Получаем запись выполнения
    task_exec = await get_task_execution_by_notification(db, notification_id)
    if not task_exec:
        # Если записи нет – создаём
        task_exec = TaskExecution(
            notification_id=notification_id,
            employee_id=employee.id,
            status=TaskExecutionStatus.NOT_STARTED
        )
        db.add(task_exec)
        await db.flush()

    # 3. Если задача ещё не начата – устанавливаем started_at = время создания уведомления
    if task_exec.status == TaskExecutionStatus.NOT_STARTED:
        task_exec.started_at = notif.created_at

    # 4. Если задача на перерыве – закрываем активный перерыв
    if task_exec.status == TaskExecutionStatus.ON_BREAK:
        stmt_break = select(TaskBreak).where(
            TaskBreak.task_execution_id == task_exec.id,
            TaskBreak.ended_at.is_(None)
        ).order_by(TaskBreak.started_at.desc()).limit(1)
        break_result = await db.execute(stmt_break)
        current_break = break_result.scalar_one_or_none()
        if current_break:
            current_break.ended_at = datetime.now()

    # 5. Устанавливаем статус COMPLETED и фиксируем время завершения
    task_exec.status = TaskExecutionStatus.COMPLETED
    task_exec.completed_at = datetime.now()

    await db.commit()
    return {"message": "Задача завершена", "completed_at": task_exec.completed_at.isoformat()}


@router.get("/tasks/{notification_id}/status")
async def get_task_status(
    notification_id: int,
    employee: models.Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    # 1. Проверяем уведомление
    stmt = select(Notification).where(Notification.id == notification_id)
    result = await db.execute(stmt)
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Уведомление не найдено")
    if notif.employee_id != employee.id:
        raise HTTPException(403, "Это не ваше уведомление")
    if notif.type != NotificationType.TASK_ASSIGNMENT:
        raise HTTPException(400, "Это уведомление не является задачей")

    # 2. Получаем запись выполнения
    task_exec = await get_task_execution_by_notification(db, notification_id)
    if not task_exec:
        # Возвращаем статус по умолчанию
        return {
            "status": TaskExecutionStatus.NOT_STARTED.value,
            "started_at": None,
            "completed_at": None
        }

    return {
        "status": task_exec.status.value,
        "started_at": task_exec.started_at.isoformat() if task_exec.started_at else None,
        "completed_at": task_exec.completed_at.isoformat() if task_exec.completed_at else None
    }

@router.get("/tasks")
async def get_my_tasks(
    employee: models.Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    # Получаем все уведомления типа task_assignment для сотрудника
    stmt = select(Notification).where(
        Notification.employee_id == employee.id,
        Notification.type == NotificationType.TASK_ASSIGNMENT,
        Notification.status == NotificationStatus.SENT
    ).order_by(Notification.created_at.desc())
    result = await db.execute(stmt)
    notifications = result.scalars().all()

    # 1. Находим ID самого старого уведомления для каждой задачи (это и есть основной исполнитель)
    task_oldest_notif = {}
    for notif in notifications:
        extra = notif.extra_data or {}
        d_id = extra.get('deal_id')
        t_id = extra.get('task_id')
        if d_id and t_id:
            key = f"{d_id}_{t_id}"
            if key not in task_oldest_notif or notif.id < task_oldest_notif[key]:
                task_oldest_notif[key] = notif.id

    # 2. Формируем ответ
    output = []
    for notif in notifications:
        task_exec = await get_task_execution_by_notification(db, notif.id)
        
        # Проверяем, является ли этот сотрудник основным исполнителем
        extra = notif.extra_data or {}
        key = f"{extra.get('deal_id')}_{extra.get('task_id')}" if extra.get('deal_id') and extra.get('task_id') else None
        is_main_executor = (task_oldest_notif.get(key) == notif.id) if key else False

        output.append({
            "id": notif.id,
            "message": notif.message,
            "created_at": notif.created_at,
            "extra_data": notif.extra_data,
            "status": task_exec.status.value if task_exec else TaskExecutionStatus.NOT_STARTED.value,
            "started_at": task_exec.started_at.isoformat() if task_exec and task_exec.started_at else None,
            "completed_at": task_exec.completed_at.isoformat() if task_exec and task_exec.completed_at else None,
            "is_main_executor": is_main_executor  # <-- НОВОЕ ПОЛЕ
        })
    return output

# employee_notifications.py (дописать в конец файла)

from sqlalchemy import select, delete
from models import Notification, NotificationType, NotificationStatus, TaskExecution, TaskExecutionStatus, Deal, Employee
from schemas import DealProductItem  # если нужно
from sse import notify_employee
import logging

@router.post("/tasks/{task_id}/assignees")
async def add_task_assignee(
    task_id: int,
    data: dict = Body(...),
    employee: models.Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    deal_id = data.get("deal_id")
    employee_id_to_add = data.get("employee_id")
    if not deal_id or not employee_id_to_add:
        raise HTTPException(400, "Необходимо указать deal_id и employee_id")

    # Проверяем, что текущий сотрудник является ОСНОВНЫМ исполнителем (первым назначенным)
    # Находим самое старое уведомление для этой задачи в этой сделке
    stmt_oldest = select(Notification.id).where(
        Notification.type == NotificationType.TASK_ASSIGNMENT,
        Notification.status == NotificationStatus.SENT,
        Notification.extra_data.op('->>')('deal_id') == str(deal_id),
        Notification.extra_data.op('->>')('task_id') == str(task_id)
    ).order_by(Notification.id.asc()).limit(1)
    oldest_result = await db.execute(stmt_oldest)
    oldest_notif_id = oldest_result.scalar()

    if not oldest_notif_id:
        raise HTTPException(404, "Нет исполнителей для этой задачи")

    # Проверяем, что текущий сотрудник – это основной исполнитель
    stmt_check = select(Notification).where(
        Notification.id == oldest_notif_id,
        Notification.employee_id == employee.id
    )
    result_check = await db.execute(stmt_check)
    if not result_check.scalar_one_or_none():
        raise HTTPException(403, "Только основной исполнитель может добавлять соисполнителей")

    # Далее код без изменений (проверка существования сотрудника, дублирования и т.д.)
    target_employee = await crud.get_employee_by_id(db, employee_id_to_add)
    if not target_employee:
        raise HTTPException(404, "Сотрудник не найден")

    # Проверяем, что он ещё не назначен на эту задачу
    stmt_existing = select(Notification).where(
        Notification.employee_id == employee_id_to_add,
        Notification.type == NotificationType.TASK_ASSIGNMENT,
        Notification.status == NotificationStatus.SENT,
        Notification.extra_data.op('->>')('deal_id') == str(deal_id),
        Notification.extra_data.op('->>')('task_id') == str(task_id)
    )
    existing = (await db.execute(stmt_existing)).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "Этот сотрудник уже назначен на задачу")

    # Находим существующее уведомление для этой задачи (чтобы скопировать данные)
    stmt_source = select(Notification).where(
        Notification.type == NotificationType.TASK_ASSIGNMENT,
        Notification.status == NotificationStatus.SENT,
        Notification.extra_data.op('->>')('deal_id') == str(deal_id),
        Notification.extra_data.op('->>')('task_id') == str(task_id)
    ).limit(1)
    source_notif = (await db.execute(stmt_source)).scalar_one_or_none()
    if not source_notif:
        raise HTTPException(404, "Исходное уведомление не найдено")

    extra_data = dict(source_notif.extra_data)
    message = source_notif.message

    new_notification = Notification(
        employee_id=employee_id_to_add,
        admin_id=employee.id,
        type=NotificationType.TASK_ASSIGNMENT,
        message=message,
        status=NotificationStatus.SENT,
        source="employee",
        extra_data=extra_data
    )
    db.add(new_notification)
    await db.flush()

    task_exec = TaskExecution(
        notification_id=new_notification.id,
        employee_id=employee_id_to_add,
        status=TaskExecutionStatus.NOT_STARTED
    )
    db.add(task_exec)
    await db.commit()

    await notify_employee(employee_id_to_add)

    return {"message": "Соисполнитель добавлен", "notification_id": new_notification.id}


@router.delete("/tasks/{task_id}/assignees/{employee_id_to_remove}")
async def remove_task_assignee(
    task_id: int,
    employee_id_to_remove: int,
    data: dict = Body(...),
    employee: models.Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    deal_id = data.get("deal_id")
    if not deal_id:
        raise HTTPException(400, "Необходимо указать deal_id")

    # Проверяем, что текущий сотрудник является ОСНОВНЫМ исполнителем
    stmt_oldest = select(Notification.id).where(
        Notification.type == NotificationType.TASK_ASSIGNMENT,
        Notification.status == NotificationStatus.SENT,
        Notification.extra_data.op('->>')('deal_id') == str(deal_id),
        Notification.extra_data.op('->>')('task_id') == str(task_id)
    ).order_by(Notification.id.asc()).limit(1)
    oldest_result = await db.execute(stmt_oldest)
    oldest_notif_id = oldest_result.scalar()

    if not oldest_notif_id:
        raise HTTPException(404, "Нет исполнителей для этой задачи")

    stmt_check = select(Notification).where(
        Notification.id == oldest_notif_id,
        Notification.employee_id == employee.id
    )
    result_check = await db.execute(stmt_check)
    if not result_check.scalar_one_or_none():
        raise HTTPException(403, "Только основной исполнитель может удалять соисполнителей")

    # Находим уведомление удаляемого сотрудника
    stmt_notif = select(Notification).where(
        Notification.employee_id == employee_id_to_remove,
        Notification.type == NotificationType.TASK_ASSIGNMENT,
        Notification.status == NotificationStatus.SENT,
        Notification.extra_data.op('->>')('deal_id') == str(deal_id),
        Notification.extra_data.op('->>')('task_id') == str(task_id)
    )
    notif = (await db.execute(stmt_notif)).scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Назначение не найдено")

    # Не даём удалить основного исполнителя (первого назначенного)
    if oldest_notif_id == notif.id:
        raise HTTPException(400, "Нельзя удалить основного исполнителя")

    # Удаляем связанные TaskExecution и Explanation
    te_stmt = select(TaskExecution).where(TaskExecution.notification_id == notif.id)
    te = (await db.execute(te_stmt)).scalar_one_or_none()
    if te:
        await db.delete(te)

    exp_stmt = select(Explanation).where(Explanation.notification_id == notif.id)
    exp = (await db.execute(exp_stmt)).scalar_one_or_none()
    if exp:
        await db.delete(exp)

    await db.delete(notif)
    await db.commit()

    return {"message": "Соисполнитель удалён"}


@router.delete("/tasks/{task_id}/assignees/{employee_id_to_remove}")
async def remove_task_assignee(
    task_id: int,
    employee_id_to_remove: int,
    data: dict = Body(...),  # ожидаем {"deal_id": int}
    employee: models.Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    deal_id = data.get("deal_id")
    if not deal_id:
        raise HTTPException(400, "Необходимо указать deal_id")

    # Проверяем, что текущий сотрудник является исполнителем этой задачи
    stmt_check = select(Notification).where(
        Notification.employee_id == employee.id,
        Notification.type == NotificationType.TASK_ASSIGNMENT,
        Notification.status == NotificationStatus.SENT,
        Notification.extra_data.op('->>')('deal_id') == str(deal_id),
        Notification.extra_data.op('->>')('task_id') == str(task_id)
    )
    result_check = await db.execute(stmt_check)
    if not result_check.scalar_one_or_none():
        raise HTTPException(403, "Вы не являетесь исполнителем этой задачи")

    # Находим уведомление удаляемого сотрудника
    stmt_notif = select(Notification).where(
        Notification.employee_id == employee_id_to_remove,
        Notification.type == NotificationType.TASK_ASSIGNMENT,
        Notification.status == NotificationStatus.SENT,
        Notification.extra_data.op('->>')('deal_id') == str(deal_id),
        Notification.extra_data.op('->>')('task_id') == str(task_id)
    )
    notif = (await db.execute(stmt_notif)).scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Назначение не найдено")

    # Не даём удалить основного исполнителя (первого назначенного)
    stmt_oldest = select(Notification.id).where(
        Notification.type == NotificationType.TASK_ASSIGNMENT,
        Notification.status == NotificationStatus.SENT,
        Notification.extra_data.op('->>')('deal_id') == str(deal_id),
        Notification.extra_data.op('->>')('task_id') == str(task_id)
    ).order_by(Notification.id.asc()).limit(1)
    oldest_id = (await db.execute(stmt_oldest)).scalar()
    if oldest_id == notif.id:
        raise HTTPException(400, "Нельзя удалить основного исполнителя")

    # Удаляем связанные TaskExecution и Explanation (если есть)
    te_stmt = select(TaskExecution).where(TaskExecution.notification_id == notif.id)
    te = (await db.execute(te_stmt)).scalar_one_or_none()
    if te:
        await db.delete(te)

    exp_stmt = select(Explanation).where(Explanation.notification_id == notif.id)
    exp = (await db.execute(exp_stmt)).scalar_one_or_none()
    if exp:
        await db.delete(exp)

    await db.delete(notif)
    await db.commit()

    return {"message": "Соисполнитель удалён"}

@router.post("/tasks/{notification_id}/break")
async def task_break(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    employee: models.Employee = Depends(get_current_employee)
):
    te = await crud.get_task_execution_by_notification(db, notification_id)
    if not te:
        raise HTTPException(404, "Task execution not found")
    if te.employee_id != employee.id:
        raise HTTPException(403, "Not your task")
    if te.status != TaskExecutionStatus.IN_PROGRESS:
        raise HTTPException(400, "Task must be in progress to start break")
    
    # Создаём запись перерыва
    new_break = TaskBreak(
        task_execution_id=te.id,
        started_at=datetime.now()
    )
    db.add(new_break)
    
    te.status = TaskExecutionStatus.ON_BREAK
    await db.commit()
    return {"message": "Task break started"}

@router.post("/tasks/{notification_id}/resume")
async def task_resume(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    employee: models.Employee = Depends(get_current_employee)
):
    te = await crud.get_task_execution_by_notification(db, notification_id)
    if not te:
        raise HTTPException(404, "Task execution not found")
    if te.employee_id != employee.id:
        raise HTTPException(403, "Not your task")
    if te.status != TaskExecutionStatus.ON_BREAK:
        raise HTTPException(400, "Task must be on break to resume")
    
    # Находим последний активный перерыв (ended_at IS NULL)
    stmt = select(TaskBreak).where(
        TaskBreak.task_execution_id == te.id,
        TaskBreak.ended_at.is_(None)
    ).order_by(TaskBreak.started_at.desc()).limit(1)
    result = await db.execute(stmt)
    current_break = result.scalar_one_or_none()
    if current_break:
        current_break.ended_at = datetime.now()
    
    te.status = TaskExecutionStatus.IN_PROGRESS
    await db.commit()
    return {"message": "Task resumed"}

@router.get("/tasks/{notification_id}/breaks")
async def get_task_breaks(
    notification_id: int,
    employee: models.Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    te = await crud.get_task_execution_by_notification(db, notification_id)
    if not te:
        raise HTTPException(404, "Task execution not found")
    if te.employee_id != employee.id:
        raise HTTPException(403, "Not your task")
    
    stmt = select(TaskBreak).where(TaskBreak.task_execution_id == te.id).order_by(TaskBreak.started_at)
    result = await db.execute(stmt)
    breaks = result.scalars().all()
    
    return [
        {
            "started_at": b.started_at.isoformat(),
            "ended_at": b.ended_at.isoformat() if b.ended_at else None,
            "duration_minutes": round((b.ended_at - b.started_at).total_seconds() / 60, 2) if b.ended_at else None
        }
        for b in breaks
    ]

from pydantic import BaseModel
from typing import List, Optional

class EmployeeCompletionDist(BaseModel):
    employee_id: int
    quantity: int

class EmployeeTaskCompletionRequest(BaseModel):
    product_type_id: int
    defect_quantity: int = 0
    defect_comment: Optional[str] = None
    distributions: List[EmployeeCompletionDist]

@router.post("/tasks/{notification_id}/completion")
async def save_or_update_task_completion(
    notification_id: int,
    data: EmployeeTaskCompletionRequest,
    employee: models.Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    """Сохранить или обновить данные о браке и распределении для сотрудника."""
    # 1. Проверяем, что уведомление принадлежит сотруднику
    notif = await db.get(Notification, notification_id)
    if not notif or notif.employee_id != employee.id:
        raise HTTPException(403, "Это не ваше уведомление")
        
    # 2. Проверяем, что сотрудник является ОСНОВНЫМ исполнителем
    extra = notif.extra_data or {}
    deal_id = extra.get('deal_id')
    task_id = extra.get('task_id')
    if not deal_id or not task_id:
        raise HTTPException(400, "Неверные данные уведомления")

    stmt_oldest = select(Notification.id).where(
        Notification.type == NotificationType.TASK_ASSIGNMENT,
        Notification.status == NotificationStatus.SENT,
        Notification.extra_data.op('->>')('deal_id') == str(deal_id),
        Notification.extra_data.op('->>')('task_id') == str(task_id)
    ).order_by(Notification.id.asc()).limit(1)
    oldest_result = await db.execute(stmt_oldest)
    oldest_id = oldest_result.scalar()
    
    if oldest_id != notification_id:
        raise HTTPException(403, "Только основной исполнитель может редактировать данные завершения")

    # 3. Сохраняем данные через существующий CRUD
    distributions = [{"employee_id": d.employee_id, "quantity": d.quantity} for d in data.distributions]
    
    try:
        await crud.create_or_update_task_completion(
            db,
            deal_id=deal_id,
            task_id=task_id,
            product_type_id=data.product_type_id,
            defect_quantity=data.defect_quantity,
            defect_comment=data.defect_comment,
            distributions=distributions
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
        
    return {"message": "Данные успешно обновлены"}