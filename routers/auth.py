from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from database import get_db
import crud
import os
from datetime import datetime, time, timedelta
import models

router = APIRouter(prefix="/api/auth", tags=["auth"])

class AdminLoginData(BaseModel):
    password: str

async def admin_required(request: Request):
    if not request.session.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

class LoginData(BaseModel):
    username: str
    password: str

@router.post("/login")
async def login(login_data: LoginData, request: Request, db: AsyncSession = Depends(get_db)):
    employee = await crud.get_employee_by_username(db, login_data.username)
    if not employee:
        raise HTTPException(404, "Сотрудник с таким логином не найден")
    if not employee.is_active:
        raise HTTPException(403, "Сотрудник деактивирован")
    if employee.password != login_data.password:
        raise HTTPException(401, "Неверный пароль")
    request.session.pop("is_admin", None)
    request.session.pop("is_monitor", None)
    request.session["employee_id"] = employee.id
    return {"message": "Успешный вход", "employee_id": employee.id, "username": employee.username, "full_name": employee.full_name}

@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"message": "Выход выполнен"}

@router.get("/profile")
async def get_profile(request: Request, db: AsyncSession = Depends(get_db)):
    employee_id = request.session.get("employee_id")
    if not employee_id:
        raise HTTPException(401, "Не авторизован")
    employee = await crud.get_employee_by_id(db, employee_id)
    if not employee:
        request.session.clear()
        raise HTTPException(404, "Сотрудник не найден")
    return {
        "id": employee.id,
        "username": employee.username,
        "full_name": employee.full_name,
        "is_active": employee.is_active,
        "is_admin": employee.is_admin,
        "is_monitor": employee.is_monitor
    }

async def get_current_employee(request: Request, db: AsyncSession = Depends(get_db)):
    employee_id = request.session.get("employee_id")
    if not employee_id:
        raise HTTPException(401, "Not authenticated")
    employee = await crud.get_employee_by_id(db, employee_id)
    if not employee:
        request.session.clear()
        raise HTTPException(401, "Employee not found")
    return employee

async def get_current_admin(request: Request, db: AsyncSession = Depends(get_db)):
    employee_id = request.session.get("employee_id")
    if employee_id:
        employee = await crud.get_employee_by_id(db, employee_id)
        if employee and employee.is_admin == 1:
            return employee
    if request.session.get("is_admin"):
        return None
    raise HTTPException(403, "Admin access required")

async def get_current_monitor(request: Request, db: AsyncSession = Depends(get_db)):
    employee_id = request.session.get("employee_id")
    if employee_id:
        employee = await crud.get_employee_by_id(db, employee_id)
        if employee and (employee.is_admin == 1 or employee.is_monitor == 1):
            return employee
    if request.session.get("is_monitor"):
        return None
    raise HTTPException(403, "Monitor access required")

@router.get("/daily-summary")
async def employee_daily_summary(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    employee_id = request.session.get("employee_id")
    if not employee_id:
        raise HTTPException(401, "Not authenticated")
    employee = await crud.get_employee_by_id(db, employee_id)
    if not employee:
        request.session.clear()
        raise HTTPException(401, "Employee not found")
    
    target_date = datetime.now().date()
    workday_start = datetime.combine(target_date, time(5, 0, 0))
    workday_end = workday_start + timedelta(days=1)
    entries = await crud.get_time_entries(db, employee_id=employee.id, start_date=workday_start, end_date=workday_end)
    entries_sorted = sorted(entries, key=lambda x: x.timestamp)
    
    status_day = "not_started"
    status_break = "not_on_break"
    total_work_sec = 0
    total_break_sec = 0
    break_count = 0
    last_break_start = None
    last_start_time = None
    in_shift = False
    in_break = False
    now = datetime.now()
    
    for entry in entries_sorted:
        ts = entry.timestamp
        action = entry.action
        
        if action == "start":
            if not in_shift:
                in_shift = True
                last_start_time = ts
                status_day = "started"
        elif action == "end":
            if in_shift:
                in_shift = False
                if last_start_time and not in_break:
                    total_work_sec += (ts - last_start_time).total_seconds()
                last_start_time = None
                status_day = "ended"
        elif action == "break_start":
            if in_shift and not in_break:
                in_break = True
                last_break_start = ts
                status_break = "on_break"
                break_count += 1
                if last_start_time:
                    total_work_sec += (ts - last_start_time).total_seconds()
                    last_start_time = None
        elif action == "break_end":
            if in_break:
                in_break = False
                status_break = "not_on_break"
                if last_break_start:
                    total_break_sec += (ts - last_break_start).total_seconds()
                    last_break_start = None
                last_start_time = ts
    
    if in_shift and not in_break and last_start_time:
        total_work_sec += (now - last_start_time).total_seconds()
    if in_break and last_break_start:
        total_break_sec += (now - last_break_start).total_seconds()
    
    worked_hours = round(total_work_sec / 3600, 2)
    break_minutes = round(total_break_sec / 60, 0)
    
    status_day_text = {
        "not_started": "❌ Рабочий день не начат",
        "started": "✅ Работаю",
        "ended": "🏁 Рабочий день завершён"
    }.get(status_day, "неизвестно")
    
    status_break_text = {
        "not_on_break": "❌ Не в перерыве",
        "on_break": "☕ В перерыве"
    }.get(status_break, "неизвестно")
    
    return {
        "status_day": status_day_text,
        "status_break": status_break_text,
        "worked_hours_current": worked_hours,
        "break_minutes_current": break_minutes,
        "break_count": break_count
    }

@router.get("/weekly-summary")
async def employee_weekly_summary(
    start_date: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    from datetime import timedelta
    employee_id = request.session.get("employee_id")
    if not employee_id:
        raise HTTPException(401, "Not authenticated")
    employee = await crud.get_employee_by_id(db, employee_id)
    if not employee:
        request.session.clear()
        raise HTTPException(401, "Employee not found")
    
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    if start.weekday() != 0:
        raise HTTPException(400, "Дата начала должна быть понедельником")
    
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    result = {
        "employee_id": employee.id,
        "full_name": employee.full_name,
        "days": [],
        "total_worked_hours": 0,
        "total_break_minutes": 0
    }
    for i in range(7):
        day_date = start + timedelta(days=i)
        workday_start = datetime.combine(day_date, time(5, 0, 0))
        workday_end = workday_start + timedelta(days=1)
        entries = await crud.get_time_entries(db, employee_id=employee.id, start_date=workday_start, end_date=workday_end)
        worked_min, break_min, _, _ = calculate_work_stats(entries)
        worked_hours = round(worked_min / 60, 2)
        result["days"].append({
            "date": day_date.isoformat(),
            "weekday": weekdays[i],
            "worked_hours": worked_hours,
            "break_minutes": break_min
        })
        result["total_worked_hours"] += worked_hours
        result["total_break_minutes"] += break_min
    return result


def calculate_work_stats(entries):
    if not entries:
        return 0, 0, None, None
    total_work_sec = 0
    total_break_sec = 0
    start_time = None
    end_time = None
    in_shift = False
    in_break = False
    last_start = None
    last_break_start = None
    
    for entry in entries:
        ts = entry.timestamp
        action = entry.action
        if action == "start":
            if not in_shift:
                in_shift = True
                last_start = ts
                if start_time is None:
                    start_time = ts
        elif action == "end":
            if in_shift:
                in_shift = False
                end_time = ts
                if last_start and not in_break:
                    total_work_sec += (ts - last_start).total_seconds()
                last_start = None
        elif action == "break_start":
            if in_shift and not in_break:
                in_break = True
                last_break_start = ts
                if last_start:
                    total_work_sec += (ts - last_start).total_seconds()
                    last_start = None
        elif action == "break_end":
            if in_break:
                in_break = False
                if last_break_start:
                    total_break_sec += (ts - last_break_start).total_seconds()
                    last_break_start = None
                last_start = ts
    
    if in_shift and not in_break and last_start:
        now = datetime.now()
        total_work_sec += (now - last_start).total_seconds()
    if in_break and last_break_start:
        now = datetime.now()
        total_break_sec += (now - last_break_start).total_seconds()
    
    worked_min = total_work_sec // 60
    break_min = total_break_sec // 60
    start_str = start_time.isoformat() if start_time else None
    end_str = end_time.isoformat() if end_time else None
    return worked_min, break_min, start_str, end_str

class PasswordChangeData(BaseModel):
    old_password: str
    new_password: str

@router.post("/change-password")
async def change_password(
    data: PasswordChangeData,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    employee_id = request.session.get("employee_id")
    if not employee_id:
        raise HTTPException(401, "Not authenticated")
    employee = await crud.get_employee_by_id(db, employee_id)
    if not employee:
        request.session.clear()
        raise HTTPException(401, "Employee not found")
    
    if employee.password != data.old_password:
        raise HTTPException(400, "Старый пароль неверен")
    
    if len(data.new_password) < 4:
        raise HTTPException(400, "Новый пароль должен содержать минимум 4 символа")
    
    employee.password = data.new_password
    await db.commit()
    return {"message": "Пароль успешно изменён"}

class MonitorLoginData(BaseModel):
    password: str