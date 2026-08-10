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
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Notification, Explanation.explanation_text)
        .outerjoin(Explanation, Explanation.notification_id == Notification.id)
        .where(
            Notification.employee_id == employee.id,
            Notification.status == NotificationStatus.SENT
        )
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