from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, desc
from pydantic import BaseModel
import barcode
from barcode.writer import ImageWriter
from barcode.errors import BarcodeError
from io import BytesIO
from typing import List, Optional
from database import get_db
import crud
from fastapi.responses import FileResponse
from datetime import datetime, time, timedelta
from routers.auth import get_current_employee, get_current_admin, get_current_monitor
import models
from sse import notify_admin_clients, notify_monitor_clients, notify_employee
from fastapi.responses import RedirectResponse
from models import Notification, NotificationType, NotificationStatus, Explanation, Employee
from sqlalchemy.orm import aliased
class EmployeeCreate(BaseModel):
    username: str
    full_name: str

class EmployeeResponse(BaseModel):
    id: int
    username: str
    full_name: str
    barcode_secret: str
    is_active: int
    password: Optional[str] = None
    is_admin: int
    is_monitor: int
    schedule_data: Optional[dict] = None

class EmployeeUpdate(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[int] = None
    password: Optional[str] = None
    barcode_secret: Optional[str] = None
    is_admin: Optional[int] = None
    is_monitor: Optional[int] = None
    schedule_data: Optional[dict] = None

class TimeEntryCreateAdmin(BaseModel):
    employee_id: int
    action: str
    timestamp: str

class TimeEntryUpdateAdmin(BaseModel):
    timestamp: str
    action: Optional[str] = None

class NotificationCreate(BaseModel):
    employee_id: int
    type: str
    message: str

class NotificationUpdate(BaseModel):
    type: Optional[str] = None
    message: Optional[str] = None
    employee_id: Optional[int] = None

class NotificationResponse(BaseModel):
    id: int
    employee_id: int
    admin_id: int
    type: str
    message: str
    status: str
    created_at: datetime
    updated_at: datetime
    explanation: Optional[str] = None
    full_name: Optional[str] = None
    created_by: Optional[str] = None

class ExplanationUpdate(BaseModel):
    explanation_text: str

page_router = APIRouter(tags=["pages"])
router = APIRouter(prefix="/api/employees", tags=["employees"], dependencies=[Depends(get_current_admin)])
public_router = APIRouter(tags=["public"])

notifications_router = APIRouter(
    prefix="/api/admin/notifications",
    tags=["notifications"],
    dependencies=[Depends(get_current_monitor)]
)

@router.get("/", response_model=List[EmployeeResponse])
async def list_employees(active_only: bool = True, db: AsyncSession = Depends(get_db)):
    employees = await crud.get_employees(db, active_only=active_only)
    return employees

@router.post("/", response_model=EmployeeResponse, status_code=201)
async def create_employee(emp_data: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    employee = await crud.create_employee(db, username=emp_data.username, full_name=emp_data.full_name)
    return employee

@router.get("/{employee_id}/barcode")
async def get_employee_barcode(employee_id: int, action: str = "start", db: AsyncSession = Depends(get_db)):
    employee = await crud.get_employee_by_id(db, employee_id)
    if not employee:
        raise HTTPException(404, detail="Employee not found")
    code = employee.barcode_secret
    try:
        ean = barcode.get_barcode_class('ean13')
        my_barcode = ean(code, writer=ImageWriter())
        barcode_options = {
            'module_width': 0.33,
            'module_height': 15.0,
            'font_size': 12,
            'text_distance': 5.0,
            'quiet_zone': 6.5,
        }
        barcode_bytes = BytesIO()
        my_barcode.write(barcode_bytes, options=barcode_options)
        barcode_bytes.seek(0)
        return Response(content=barcode_bytes.getvalue(), media_type="image/png")
    except BarcodeError as e:
        raise HTTPException(400, detail=f"Invalid barcode: {str(e)}")

@router.put("/{employee_id}", response_model=EmployeeResponse)
async def update_employee(employee_id: int, update_data: EmployeeUpdate, db: AsyncSession = Depends(get_db)):
    employee = await crud.get_employee_by_id(db, employee_id)
    if not employee:
        raise HTTPException(404, detail="Employee not found")
    if update_data.username is not None:
        employee.username = update_data.username
    if update_data.full_name is not None:
        employee.full_name = update_data.full_name
    if update_data.is_active is not None:
        employee.is_active = update_data.is_active
    if update_data.password is not None:
        employee.password = update_data.password
    if update_data.barcode_secret is not None:
        employee.barcode_secret = update_data.barcode_secret
    if update_data.is_admin is not None:
        employee.is_admin = update_data.is_admin
    if update_data.is_monitor is not None:
        employee.is_monitor = update_data.is_monitor
    if update_data.schedule_data is not None:
        employee.schedule_data = update_data.schedule_data
    await db.commit()
    await db.refresh(employee)
    return employee

@router.delete("/{employee_id}", status_code=204)
async def delete_employee(employee_id: int, permanent: bool = False, db: AsyncSession = Depends(get_db)):
    employee = await crud.get_employee_by_id(db, employee_id)
    if not employee:
        raise HTTPException(404, detail="Employee not found")
    if permanent:
        await crud.delete_employee(db, employee_id)
    else:
        await crud.deactivate_employee(db, employee_id)
    return Response(status_code=204)

@page_router.get("/admin", include_in_schema=False)
async def admin_page(request: Request, db: AsyncSession = Depends(get_db)):
    employee_id = request.session.get("employee_id")
    if employee_id:
        employee = await crud.get_employee_by_id(db, employee_id)
        if employee and employee.is_admin == 1:
            return FileResponse(
                "templates/admin.html",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
    return RedirectResponse(url="/static/login.html", status_code=302)

@public_router.get("/api/reports/daily")
async def daily_report(date: str, db: AsyncSession = Depends(get_db)):
    target_date = datetime.strptime(date, "%Y-%m-%d").date()
    workday_start = datetime.combine(target_date, time(5, 0, 0))
    workday_end = workday_start + timedelta(days=1)
    now = datetime.now()
    interval = await crud.get_rounding_interval(db)

    employees = await crud.get_employees(db, active_only=True)
    if not employees:
        return []

    stmt = select(models.TimeEntry).where(
        models.TimeEntry.timestamp >= workday_start,
        models.TimeEntry.timestamp < workday_end
    ).order_by(models.TimeEntry.employee_id, models.TimeEntry.timestamp)
    result = await db.execute(stmt)
    all_entries = result.scalars().all()

    entries_by_employee = {}
    for entry in all_entries:
        entries_by_employee.setdefault(entry.employee_id, []).append(entry)

    result = []
    for emp in employees:
        entries = entries_by_employee.get(emp.id, [])

        total_work_sec = 0
        total_break_sec = 0
        break_count = 0
        last_start_time = None
        last_break_start = None
        in_shift = False
        in_break = False
        status_day = "not_started"
        status_break = "not_on_break"
        last_entry_time = None
        last_entry_action = None
        first_start_time = None

        for entry in entries:
            ts = entry.timestamp
            action = entry.action
            last_entry_time = ts
            last_entry_action = action

            if action == "start":
                if not in_shift:
                    in_shift = True
                    last_start_time = ts
                    status_day = "started"
                    if first_start_time is None:
                        first_start_time = ts
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

        if target_date == now.date():
            end_limit = now if now < workday_end else workday_end
            if in_shift and not in_break and last_start_time:
                total_work_sec += (end_limit - last_start_time).total_seconds()
            if in_break and last_break_start:
                total_break_sec += (end_limit - last_break_start).total_seconds()
        else:
            if in_shift and not in_break and last_start_time:
                total_work_sec += (workday_end - last_start_time).total_seconds()
            if in_break and last_break_start:
                total_break_sec += (workday_end - last_break_start).total_seconds()
            if in_shift:
                status_day = "ended"

        raw_minutes = int(total_work_sec // 60)
        rounded_minutes = crud.floor_round_minutes(int(raw_minutes), interval)

        def format_minutes_to_hhmm(minutes):
            h = minutes // 60
            m = minutes % 60
            return f"{h:02d}:{m:02d}"

        worked_display = f"{format_minutes_to_hhmm(rounded_minutes)} ({format_minutes_to_hhmm(raw_minutes)})"
        worked_hours = round(total_work_sec / 3600, 2)
        break_minutes = round(total_break_sec / 60, 0)

        status_day_text = {
            "not_started": "❌ не начал",
            "started": "✅ работает",
            "ended": "🏁 завершил"
        }.get(status_day, "неизвестно")

        status_break_text = {
            "not_on_break": "",
            "on_break": "☕ в перерыве"
        }.get(status_break, "неизвестно")

        result.append({
            "employee_id": emp.id,
            "full_name": emp.full_name,
            "status_day": status_day_text,
            "status_break": status_break_text,
            "last_entry_time": last_entry_time.isoformat() if last_entry_time else None,
            "last_entry_action": last_entry_action,
            "first_start_time": first_start_time.isoformat() if first_start_time else None,
            "last_break_start": last_break_start.isoformat() if last_break_start else None,
            "worked_hours_current": worked_hours,
            "break_minutes_current": break_minutes,
            "break_count": break_count,
            "worked_display": worked_display,
            "worked_minutes_raw": raw_minutes,
            "worked_hours_raw": round(raw_minutes / 60, 2),
            "worked_hours_rounded": round(rounded_minutes / 60, 2)
        })
    return result

@public_router.get("/api/reports/weekly")
async def weekly_report(start_date: str, admin: Optional[models.Employee] = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    from datetime import timedelta, time
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    if start.weekday() != 0:
        raise HTTPException(400, "Дата начала должна быть понедельником")
    employees = await crud.get_employees(db, active_only=True)
    interval = await crud.get_rounding_interval(db)

    def format_minutes_to_hhmm(minutes):
        minutes = int(minutes)
        h = minutes // 60
        m = minutes % 60
        return f"{h:02d}:{m:02d}"

    week_start = datetime.combine(start, time(5, 0, 0))
    week_end = week_start + timedelta(days=7)

    stmt = select(models.TimeEntry).where(
        models.TimeEntry.timestamp >= week_start,
        models.TimeEntry.timestamp < week_end
    ).order_by(models.TimeEntry.employee_id, models.TimeEntry.timestamp)
    result = await db.execute(stmt)
    all_entries = result.scalars().all()

    entries_by_employee = {}
    for entry in all_entries:
        entries_by_employee.setdefault(entry.employee_id, []).append(entry)

    result = []
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    for emp in employees:
        emp_data = {
            "employee_id": emp.id,
            "full_name": emp.full_name,
            "days": [],
            "total_rounded_minutes": 0,
            "total_raw_minutes": 0,
            "total_break_minutes": 0
        }
        entries = entries_by_employee.get(emp.id, [])

        for i in range(7):
            day_date = start + timedelta(days=i)
            workday_start = datetime.combine(day_date, time(5, 0, 0))
            workday_end = workday_start + timedelta(days=1)
            day_entries = [e for e in entries if workday_start <= e.timestamp < workday_end]

            total_work_sec = 0
            total_break_sec = 0
            last_start_time = None
            last_break_start = None
            in_shift = False
            in_break = False
            now = datetime.now()
            if day_date == now.date():
                day_cutoff = now if now < workday_end else workday_end
            else:
                day_cutoff = workday_end
            first_start_time = None
            end_time = None
            break_count = 0

            for entry in day_entries:
                ts = entry.timestamp
                action = entry.action
                if action == "start":
                    if not in_shift:
                        in_shift = True
                        last_start_time = ts
                        if first_start_time is None:
                            first_start_time = ts
                elif action == "end":
                    if in_shift:
                        in_shift = False
                        if last_start_time and not in_break:
                            total_work_sec += (ts - last_start_time).total_seconds()
                        last_start_time = None
                        end_time = ts
                elif action == "break_start":
                    if in_shift and not in_break:
                        in_break = True
                        last_break_start = ts
                        break_count += 1
                        if last_start_time:
                            total_work_sec += (ts - last_start_time).total_seconds()
                            last_start_time = None
                elif action == "break_end":
                    if in_break:
                        in_break = False
                        if last_break_start:
                            total_break_sec += (ts - last_break_start).total_seconds()
                            last_break_start = None
                        last_start_time = ts

            if in_shift and not in_break and last_start_time:
                total_work_sec += (day_cutoff - last_start_time).total_seconds()
            if in_break and last_break_start:
                total_break_sec += (day_cutoff - last_break_start).total_seconds()

            raw_minutes = int(total_work_sec // 60)
            rounded_minutes = crud.floor_round_minutes(raw_minutes, interval)
            worked_display = f"{format_minutes_to_hhmm(rounded_minutes)} ({format_minutes_to_hhmm(raw_minutes)})"
            worked_hours = round(total_work_sec / 3600, 2)
            break_minutes = round(total_break_sec / 60, 0)

            emp_data["total_rounded_minutes"] += rounded_minutes
            emp_data["total_raw_minutes"] += raw_minutes
            emp_data["total_break_minutes"] += break_minutes

            emp_data["days"].append({
                "date": day_date.isoformat(),
                "weekday": weekdays[i],
                "worked_hours": worked_hours,
                "break_minutes": break_minutes,
                "first_start_time": first_start_time.isoformat() if first_start_time else None,
                "end_time": end_time.isoformat() if end_time else None,
                "break_count": break_count,
                "worked_display": worked_display,
                "worked_minutes_raw": raw_minutes,
                "worked_hours_raw": round(raw_minutes / 60, 2),
                "worked_hours_rounded": round(rounded_minutes / 60, 2)
            })
        total_display = f"{format_minutes_to_hhmm(emp_data['total_rounded_minutes'])} ({format_minutes_to_hhmm(emp_data['total_raw_minutes'])})"
        emp_data["total_worked_display"] = total_display
        emp_data["total_worked_hours"] = round(emp_data["total_raw_minutes"] / 60, 2)
        emp_data["total_break_hours"] = round(emp_data["total_break_minutes"] / 60, 2)
        result.append(emp_data)
    return result

@public_router.get("/api/reports/employee/{employee_id}")
async def employee_detail(employee_id: int, date: str, request: Request, db: AsyncSession = Depends(get_db)):
    session_employee_id = request.session.get("employee_id")
    is_admin_session = request.session.get("is_admin", False)
    user_is_admin = is_admin_session
    if not user_is_admin and session_employee_id:
        employee = await crud.get_employee_by_id(db, session_employee_id)
        if employee and employee.is_admin == 1:
            user_is_admin = True
    if not user_is_admin and session_employee_id != employee_id:
        raise HTTPException(403, "You can only view your own reports")
    emp = await crud.get_employee_by_id(db, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    target_date = datetime.strptime(date, "%Y-%m-%d").date()
    workday_start = datetime.combine(target_date, time(5, 0, 0))
    workday_end = workday_start + timedelta(days=1)
    entries = await crud.get_time_entries(db, employee_id=employee_id, start_date=workday_start, end_date=workday_end)
    entries_list = [
        {
            "id": e.id,
            "timestamp": e.timestamp.isoformat(),
            "action": e.action,
            "source": e.source
        }
        for e in entries
    ]
    worked, breaks, _, _ = calculate_work_stats(entries)
    return {
        "employee_id": employee_id,
        "full_name": emp.full_name,
        "date": date,
        "entries": entries_list,
        "worked_hours": round(worked / 60, 2),
        "break_minutes": breaks
    }

@public_router.get("/api/employee/daily-summary")
async def employee_daily_summary(
    employee: models.Employee = Depends(get_current_employee),
    db: AsyncSession = Depends(get_db)
):
    target_date = datetime.now().date()
    workday_start = datetime.combine(target_date, time(5, 0, 0))
    workday_end = workday_start + timedelta(days=1)
    entries = await crud.get_time_entries(db, employee_id=employee.id, start_date=workday_start, end_date=workday_end)
    entries_sorted = sorted(entries, key=lambda x: x.timestamp)
    
    status_day = "not_started"
    status_break = "not_on_break"
    last_break_start = None
    total_work_sec = 0
    total_break_sec = 0
    break_count = 0
    last_start_time = None
    in_shift = False
    in_break = False
    now = datetime.now()
    
    for entry in entries_sorted:
        if entry.action == "start":
            if not in_shift:
                in_shift = True
                last_start_time = entry.timestamp
                status_day = "started"
        elif entry.action == "end":
            if in_shift:
                in_shift = False
                if last_start_time:
                    total_work_sec += (entry.timestamp - last_start_time).total_seconds()
                    last_start_time = None
                status_day = "ended"
        elif entry.action == "break_start":
            if in_shift and not in_break:
                in_break = True
                last_break_start = entry.timestamp
                status_break = "on_break"
                break_count += 1
        elif entry.action == "break_end":
            if in_break:
                in_break = False
                if last_break_start:
                    total_break_sec += (entry.timestamp - last_break_start).total_seconds()
                    last_break_start = None
                status_break = "not_on_break"
    
    if in_shift and last_start_time:
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

@public_router.post("/api/admin/timelog", status_code=201)
async def admin_create_timelog(data: TimeEntryCreateAdmin, admin: Optional[models.Employee] = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    employee = await crud.get_employee_by_id(db, data.employee_id)
    if not employee:
        raise HTTPException(404, "Employee not found")
    try:
        dt = datetime.fromisoformat(data.timestamp)
    except ValueError:
        raise HTTPException(400, "Invalid timestamp format. Use ISO format.")
    source_prefix = f"admin({admin.full_name})" if admin else "admin"
    print(f"DEBUG: admin = {admin}, type = {type(admin)}")
    entry = await crud.create_time_entry_admin(db, data.employee_id, data.action, dt, source=source_prefix)
    await notify_admin_clients()
    await notify_monitor_clients()
    return {"status": "ok", "entry_id": entry.id}

@public_router.put("/api/admin/timelog/{entry_id}")
async def admin_update_timelog(
    entry_id: int,
    data: TimeEntryUpdateAdmin,
    admin: Optional[models.Employee] = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    try:
        dt = datetime.fromisoformat(data.timestamp)
    except ValueError:
        raise HTTPException(400, "Invalid timestamp format. Use ISO format.")
    
    stmt = select(models.TimeEntry).where(models.TimeEntry.id == entry_id)
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Entry not found")
    
    entry.timestamp = dt
    if data.action is not None:
        entry.action = data.action
    entry.source = f"admin({admin.full_name})" if admin else "admin"
    
    await db.commit()
    await notify_admin_clients()
    await notify_monitor_clients()
    await db.refresh(entry)
    return {
        "status": "ok",
        "entry_id": entry.id,
        "new_timestamp": entry.timestamp.isoformat(),
        "new_action": entry.action
    }

@public_router.delete("/api/admin/timelog/{entry_id}", status_code=204)
async def admin_delete_timelog(entry_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await crud.delete_time_entry(db, entry_id)
        await notify_admin_clients()
        await notify_monitor_clients()
    except ValueError:
        raise HTTPException(404, "Entry not found")
    return Response(status_code=204)

class PasswordResetResponse(BaseModel):
    new_password: str

@router.post("/{employee_id}/reset-password", response_model=PasswordResetResponse)
async def reset_employee_password(employee_id: int, db: AsyncSession = Depends(get_db)):
    employee = await crud.get_employee_by_id(db, employee_id)
    if not employee:
        raise HTTPException(404, "Employee not found")
    new_password = crud.generate_random_password(6)
    await crud.set_employee_password(db, employee_id, new_password)
    return {"new_password": new_password}

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

@public_router.get("/api/admin/recent-entries")
async def get_recent_entries(
    limit: int = 100,
    employee_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    admin: Optional[models.Employee] = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(
        models.TimeEntry.id,
        models.TimeEntry.employee_id,
        models.TimeEntry.timestamp,
        models.TimeEntry.action,
        models.TimeEntry.source,
        models.Employee.full_name,
        models.Employee.username
    ).join(
        models.Employee, models.TimeEntry.employee_id == models.Employee.id
    )
    
    if employee_id is not None:
        stmt = stmt.where(models.TimeEntry.employee_id == employee_id)
    
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            start_datetime = datetime.combine(start_dt, time(5, 0, 0))
            stmt = stmt.where(models.TimeEntry.timestamp >= start_datetime)
        except ValueError:
            raise HTTPException(400, "Invalid start_date format, use YYYY-MM-DD")
    
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            end_datetime = datetime.combine(end_dt, time(5, 0, 0)) + timedelta(days=1)
            stmt = stmt.where(models.TimeEntry.timestamp < end_datetime)
        except ValueError:
            raise HTTPException(400, "Invalid end_date format, use YYYY-MM-DD")
    
    stmt = stmt.order_by(desc(models.TimeEntry.timestamp)).limit(limit * 2)
    result = await db.execute(stmt)
    rows = result.all()
    
    entries = []
    for row in rows:
        entries.append({
            "id": row.id,
            "employee_id": row.employee_id,
            "timestamp": row.timestamp,
            "action": row.action,
            "source": row.source,
            "full_name": row.full_name,
            "username": row.username
        })
    entries.sort(key=lambda x: x["timestamp"])
    
    from collections import defaultdict
    break_counter = defaultdict(lambda: defaultdict(int))
    break_start_time = {}
    
    for e in entries:
        emp_id = e["employee_id"]
        date = e["timestamp"].date()
        if e["action"] == "break_start":
            break_counter[emp_id][date] += 1
            e["break_number"] = break_counter[emp_id][date]
            break_start_time[(emp_id, date, e["break_number"])] = e["timestamp"]
        elif e["action"] == "break_end":
            last_num = break_counter[emp_id][date]
            if last_num > 0:
                e["break_number"] = last_num
                start_key = (emp_id, date, last_num)
                if start_key in break_start_time:
                    duration = e["timestamp"] - break_start_time[start_key]
                    total_seconds = int(duration.total_seconds())
                    minutes = total_seconds // 60
                    hours = minutes // 60
                    mins = minutes % 60
                    e["break_duration"] = f"{hours:02d}:{mins:02d}"
    
    entries.sort(key=lambda x: x["timestamp"], reverse=True)
    entries = entries[:limit]
    
    action_map = {
        "start": "Начало рабочего дня",
        "break_start": "Начало перерыва",
        "break_end": "Конец перерыва",
        "end": "Конец рабочего дня"
    }
    
    result_list = []
    for e in entries:
        item = {
            "id": e["id"],
            "timestamp": e["timestamp"].isoformat(),
            "action": action_map.get(e["action"], e["action"]),
            "action_code": e["action"],
            "source": e["source"],
            "full_name": e["full_name"],
            "username": e["username"]
        }
        if e.get("break_number"):
            item["break_number"] = e["break_number"]
        if e.get("break_duration"):
            item["break_duration"] = e["break_duration"]
        result_list.append(item)
    
    return result_list

@page_router.get("/monitor", include_in_schema=False)
async def monitor_page(request: Request, monitor: Optional[models.Employee] = Depends(get_current_monitor)):
    if monitor is None and not request.session.get("is_monitor"):
        return FileResponse("static/monitor_login.html")
    return FileResponse(
        "static/monitor.html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

class RoundingRequest(BaseModel):
    interval_minutes: int

@public_router.get("/api/admin/rounding")
async def get_rounding_interval_api(db: AsyncSession = Depends(get_db)):
    interval = await crud.get_rounding_interval(db)
    return {"interval_minutes": interval}

@public_router.post("/api/admin/rounding")
async def set_rounding_interval_api(
    data: RoundingRequest,
    admin: models.Employee = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    if not admin:
        raise HTTPException(403, "Admin access required")
    if data.interval_minutes < 1 or data.interval_minutes > 60:
        raise HTTPException(400, "Interval must be 1-60 minutes")
    await crud.set_rounding_interval(db, data.interval_minutes)
    return {"message": "ok"}

@notifications_router.post("/", response_model=dict)
async def create_notification(
    data: NotificationCreate,
    current_user: models.Employee = Depends(get_current_monitor),
    db: AsyncSession = Depends(get_db)
):
    try:
        notif_type = NotificationType(data.type)
    except ValueError:
        raise HTTPException(400, "Invalid notification type")
    
    employee = await crud.get_employee_by_id(db, data.employee_id)
    if not employee:
        raise HTTPException(404, "Employee not found")
    
    if current_user.is_admin:
        admin_id = current_user.id
    else:
        admin_stmt = select(models.Employee).where(models.Employee.is_admin == 1).limit(1)
        admin_result = await db.execute(admin_stmt)
        system_admin = admin_result.scalar_one_or_none()
        if not system_admin:
            raise HTTPException(500, "No admin found in system")
        admin_id = system_admin.id
    
    notification = Notification(
        employee_id=data.employee_id,
        admin_id=admin_id,
        type=notif_type,
        message=data.message,
        status=NotificationStatus.DRAFT,
        source="admin"
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    await notify_admin_clients()
    return {"id": notification.id, "status": notification.status.value}

@notifications_router.get("/", response_model=List[NotificationResponse])
async def list_notifications(
    status: Optional[str] = None,
    employee_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    AdminEmp = aliased(models.Employee, name="admin_emp")

    stmt = (
        select(
            Notification,
            Explanation.explanation_text.label("explanation_text"),
            models.Employee.full_name.label("emp_full_name"),
            AdminEmp.full_name.label("admin_full_name")
        )
        .outerjoin(Explanation, Explanation.notification_id == Notification.id)
        .outerjoin(models.Employee, models.Employee.id == Notification.employee_id)
        .outerjoin(AdminEmp, AdminEmp.id == Notification.admin_id)
        .order_by(Notification.created_at.desc())
    )

    if status:
        try:
            status_enum = NotificationStatus(status)
            stmt = stmt.where(Notification.status == status_enum)
        except ValueError:
            raise HTTPException(400, "Invalid status value")

    if employee_id is not None:
        stmt = stmt.where(Notification.employee_id == employee_id)

    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            stmt = stmt.where(Notification.created_at >= datetime.combine(start_dt, time(5, 0, 0)))
        except ValueError:
            raise HTTPException(400, "Invalid start_date format, use YYYY-MM-DD")

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            stmt = stmt.where(Notification.created_at < datetime.combine(end_dt, time(5, 0, 0)) + timedelta(days=1))
        except ValueError:
            raise HTTPException(400, "Invalid end_date format, use YYYY-MM-DD")

    result = await db.execute(stmt)
    rows = result.all()

    response = []
    for notif, exp_text, emp_name, admin_name in rows:
        created_by = "Авто" if notif.source == "auto" else (admin_name or "Админ")
        
        response.append(NotificationResponse(
            id=notif.id,
            employee_id=notif.employee_id,
            admin_id=notif.admin_id,
            type=notif.type.value,
            message=notif.message,
            status=notif.status.value,
            created_at=notif.created_at,
            updated_at=notif.updated_at,
            explanation=exp_text,
            full_name=emp_name,
            created_by=created_by
        ))
    return response

@notifications_router.put("/{notification_id}", response_model=dict)
async def update_notification(
    notification_id: int,
    data: NotificationUpdate,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Notification).where(Notification.id == notification_id)
    result = await db.execute(stmt)
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Notification not found")
    
    if data.type is not None:
        try:
            notif.type = NotificationType(data.type)
        except ValueError:
            raise HTTPException(400, "Invalid type")
    if data.message is not None:
        notif.message = data.message
    if data.employee_id is not None:
        emp_stmt = select(Employee).where(Employee.id == data.employee_id)
        emp_res = await db.execute(emp_stmt)
        if not emp_res.scalar_one_or_none():
            raise HTTPException(404, "Employee not found")
        if data.employee_id is not None and data.employee_id != notif.employee_id:
            from models import Explanation
            exp_stmt = select(Explanation).where(Explanation.notification_id == notification_id)
            exp_result = await db.execute(exp_stmt)
            explanation = exp_result.scalar_one_or_none()
            if explanation:
                await db.delete(explanation)
        notif.employee_id = data.employee_id
    if notif.status in (NotificationStatus.SENT, NotificationStatus.REJECTED):
        notif.status = NotificationStatus.DRAFT
    
    notif.updated_at = datetime.now()
    await db.commit()
    await notify_admin_clients()
    return {"id": notif.id, "status": notif.status.value}

@notifications_router.post("/{notification_id}/approve", response_model=dict)
async def approve_notification(
    notification_id: int,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Notification).where(Notification.id == notification_id)
    result = await db.execute(stmt)
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Notification not found")
    if notif.status != NotificationStatus.DRAFT:
        raise HTTPException(400, "Only draft notifications can be approved")
    notif.status = NotificationStatus.SENT
    notif.updated_at = datetime.now()
    await db.commit()
    await notify_employee(notif.employee_id)
    await notify_admin_clients()
    return {"id": notif.id, "status": notif.status.value}

@notifications_router.post("/{notification_id}/reject", response_model=dict)
async def reject_notification(
    notification_id: int,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Notification).where(Notification.id == notification_id)
    result = await db.execute(stmt)
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Notification not found")
    if notif.status != NotificationStatus.DRAFT:
        raise HTTPException(400, "Only draft notifications can be rejected")
    notif.status = NotificationStatus.REJECTED
    notif.updated_at = datetime.now()
    await db.commit()
    await notify_admin_clients()
    return {"id": notif.id, "status": notif.status.value}

@notifications_router.get("/{notification_id}/explanation", response_model=dict)
async def get_explanation(
    notification_id: int,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Explanation).where(Explanation.notification_id == notification_id)
    result = await db.execute(stmt)
    explanation = result.scalar_one_or_none()
    if not explanation:
        raise HTTPException(404, "Explanation not found")
    return {
        "id": explanation.id,
        "notification_id": explanation.notification_id,
        "employee_id": explanation.employee_id,
        "explanation_text": explanation.explanation_text,
        "created_at": explanation.created_at
    }

@notifications_router.delete("/{notification_id}", status_code=204)
async def delete_notification(
    notification_id: int,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Notification).where(Notification.id == notification_id)
    result = await db.execute(stmt)
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Notification not found")
    exp_stmt = select(Explanation).where(Explanation.notification_id == notification_id)
    exp_result = await db.execute(exp_stmt)
    explanation = exp_result.scalar_one_or_none()
    if explanation:
        await db.delete(explanation)
    
    await db.delete(notif)
    await db.commit()
    await notify_admin_clients()
    return Response(status_code=204)

@notifications_router.put("/{notification_id}/explanation", response_model=dict)
async def update_explanation(
    notification_id: int,
    data: ExplanationUpdate,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Explanation).where(Explanation.notification_id == notification_id)
    result = await db.execute(stmt)
    explanation = result.scalar_one_or_none()
    if not explanation:
        raise HTTPException(404, "Explanation not found")
    explanation.explanation_text = data.explanation_text
    explanation.created_at = datetime.now()
    await db.commit()
    await notify_admin_clients()
    return {"message": "Updated"}

@notifications_router.post("/{notification_id}/explanation", response_model=dict)
async def create_explanation(
    notification_id: int,
    data: ExplanationUpdate,
    db: AsyncSession = Depends(get_db)
):
    notif_stmt = select(Notification).where(Notification.id == notification_id)
    notif_res = await db.execute(notif_stmt)
    notif = notif_res.scalar_one_or_none()
    if not notif:
        raise HTTPException(404, "Notification not found")
    exp_stmt = select(Explanation).where(Explanation.notification_id == notification_id)
    exp_res = await db.execute(exp_stmt)
    if exp_res.scalar_one_or_none():
        raise HTTPException(400, "Explanation already exists, use PUT")
    
    explanation = Explanation(
        notification_id=notification_id,
        employee_id=notif.employee_id,
        explanation_text=data.explanation_text
    )
    db.add(explanation)
    await db.commit()
    await notify_admin_clients()
    return {"message": "Created"}