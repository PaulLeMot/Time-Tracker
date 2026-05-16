from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from database import get_db
from routers.auth import get_current_employee
import models
from models import Notification, Explanation, NotificationStatus

router = APIRouter(prefix="/api/employee", tags=["employee"])

class NotificationResponse(BaseModel):
    id: int
    type: str
    message: str
    created_at: datetime
    has_explanation: bool

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
    stmt = select(Notification).where(
        Notification.employee_id == employee.id,
        Notification.status == NotificationStatus.SENT
    ).order_by(Notification.created_at.desc())
    result = await db.execute(stmt)
    notifications = result.scalars().all()

    response = []
    for n in notifications:
        exp_stmt = select(Explanation).where(Explanation.notification_id == n.id)
        exp_result = await db.execute(exp_stmt)
        has_exp = exp_result.scalar_one_or_none() is not None
        response.append(NotificationResponse(
            id=n.id,
            type=n.type.value,
            message=n.message,
            created_at=n.created_at,
            has_explanation=has_exp
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