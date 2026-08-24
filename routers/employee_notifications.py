from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from database import get_db
from routers.auth import get_current_employee
import models
from models import Notification, Explanation, NotificationStatus, NotificationType
from sse import notify_admin_clients
from models import TaskExecution, TaskExecutionStatus
from crud import get_task_execution_by_notification, update_task_execution_status

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
        raise HTTPException(404, "Запись о выполнении не найдена")

    # 3. Проверяем статус
    if task_exec.status == TaskExecutionStatus.NOT_STARTED:
        raise HTTPException(400, "Задача ещё не начата")
    if task_exec.status == TaskExecutionStatus.COMPLETED:
        raise HTTPException(400, "Задача уже завершена")

    # 4. Обновляем статус и время завершения
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

    # Для каждого уведомления подгружаем статус выполнения
    output = []
    for notif in notifications:
        task_exec = await get_task_execution_by_notification(db, notif.id)
        output.append({
            "id": notif.id,
            "message": notif.message,
            "created_at": notif.created_at,
            "extra_data": notif.extra_data,
            "status": task_exec.status.value if task_exec else TaskExecutionStatus.NOT_STARTED.value,
            "started_at": task_exec.started_at.isoformat() if task_exec and task_exec.started_at else None,
            "completed_at": task_exec.completed_at.isoformat() if task_exec and task_exec.completed_at else None
        })
    return output