from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, desc
from pydantic import BaseModel
import barcode
from barcode.writer import ImageWriter
from io import BytesIO
from typing import List, Optional
from database import get_db
import crud
from fastapi.responses import FileResponse
from datetime import datetime
from routers.auth import admin_required
from routers.auth import get_current_employee
import models
class EmployeeCreate(BaseModel):
    username: str
    full_name: str

class EmployeeResponse(BaseModel):
    id: int
    username: str
    full_name: str
    qr_code_secret: str
    is_active: int
    password: Optional[str] = None

class EmployeeUpdate(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[int] = None
    password: Optional[str] = None

class TimeEntryCreateAdmin(BaseModel):
    employee_id: int
    action: str
    timestamp: str

class TimeEntryUpdateAdmin(BaseModel):
    timestamp: str

page_router = APIRouter(tags=["pages"])
router = APIRouter(prefix="/api/employees", tags=["employees"], dependencies=[Depends(admin_required)])
public_router = APIRouter(tags=["public"])

@router.get("/", response_model=List[EmployeeResponse])
async def list_employees(active_only: bool = True, db: AsyncSession = Depends(get_db)):
    employees = await crud.get_employees(db, active_only=active_only)
    return employees

@router.post("/", response_model=EmployeeResponse, status_code=201)
async def create_employee(emp_data: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    employee = await crud.create_employee(db, username=emp_data.username, full_name=emp_data.full_name)
    return employee

@router.get("/{employee_id}/qr")
async def get_employee_qr(employee_id: int, action: str = "start", db: AsyncSession = Depends(get_db)):
    employee = await crud.get_employee_by_id(db, employee_id)
    if not employee:
        raise HTTPException(404, detail="Employee not found")
    barcode_data = str(employee_id)
    barcode_class = barcode.get_barcode_class('code128')
    my_barcode = barcode_class(barcode_data, writer=ImageWriter())
    barcode_options = {
        'module_width': 0.3,
        'module_height': 15.0,
        'font_size': 12,
        'text_distance': 5.0,
        'quiet_zone': 6.5,
    }
    barcode_bytes = BytesIO()
    my_barcode.write(barcode_bytes, options=barcode_options)
    barcode_bytes.seek(0)
    return Response(content=barcode_bytes.getvalue(), media_type="image/png")

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
async def admin_page(request: Request):
    return FileResponse(
        "templates/admin.html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@public_router.get("/api/reports/daily")
async def daily_report(date: str, db: AsyncSession = Depends(get_db)):
    employees = await crud.get_employees(db, active_only=True)
    target_date = datetime.strptime(date, "%Y-%m-%d").date()
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())
    
    result = []
    for emp in employees:
        entries = await crud.get_time_entries(db, employee_id=emp.id, start_date=start_of_day, end_date=end_of_day)
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
        
        for entry in entries_sorted:
            if entry.action == "start":
                if not in_shift:
                    in_shift = True
                    last_start_time = entry.timestamp
                    status_day = "started"
            elif entry.action == "end":
                if in_shift:
                    in_shift = False
                    if last_start_time and not in_break:
                        total_work_sec += (entry.timestamp - last_start_time).total_seconds()
                    last_start_time = None
                    status_day = "ended"
            elif entry.action == "break_start":
                if in_shift and not in_break:
                    in_break = True
                    last_break_start = entry.timestamp
                    status_break = "on_break"
                    break_count += 1
                    if last_start_time:
                        total_work_sec += (entry.timestamp - last_start_time).total_seconds()
                        last_start_time = None
            elif entry.action == "break_end":
                if in_break:
                    in_break = False
                    status_break = "not_on_break"
                    if last_break_start:
                        total_break_sec += (entry.timestamp - last_break_start).total_seconds()
                        last_break_start = None
                    last_start_time = entry.timestamp
        
        # Если смена активна, завершаем её в конце дня
        if in_shift and last_start_time:
            if not in_break:
                total_work_sec += (end_of_day - last_start_time).total_seconds()
            else:
                total_break_sec += (end_of_day - last_break_start).total_seconds()
            status_day = "ended"
        
        worked_hours = round(total_work_sec / 3600, 2)
        break_minutes = round(total_break_sec / 60, 0)
        
        status_day_text = {
            "not_started": "❌ не начал",
            "started": "✅ работает",
            "ended": "🏁 завершил"
        }.get(status_day, "неизвестно")
        
        status_break_text = {
            "not_on_break": "🔵 не в перерыве",
            "on_break": "☕ в перерыве"
        }.get(status_break, "неизвестно")
        
        result.append({
            "employee_id": emp.id,
            "full_name": emp.full_name,
            "status_day": status_day_text,
            "status_break": status_break_text,
            "last_break_start": last_break_start.isoformat() if last_break_start else None,
            "worked_hours_current": worked_hours,
            "break_minutes_current": break_minutes,
            "break_count": break_count
        })
    return result

@public_router.get("/api/reports/weekly")
async def weekly_report(start_date: str, request: Request, db: AsyncSession = Depends(get_db)):
    if not request.session.get("is_admin", False):
        raise HTTPException(403, "Admin access required")
    from datetime import timedelta, date as date_type
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    if start.weekday() != 0:
        raise HTTPException(400, "Дата начала должна быть понедельником")
    end = start + timedelta(days=6)
    employees = await crud.get_employees(db, active_only=True)
    
    result = []
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    
    for emp in employees:
        emp_data = {
            "employee_id": emp.id,
            "full_name": emp.full_name,
            "days": [],
            "total_worked_hours": 0,
            "total_break_minutes": 0
        }
        for i in range(7):
            day_date = start + timedelta(days=i)
            start_of_day = datetime.combine(day_date, datetime.min.time())
            end_of_day = datetime.combine(day_date, datetime.max.time())
            entries = await crud.get_time_entries(db, employee_id=emp.id, start_date=start_of_day, end_date=end_of_day)
            worked_min, break_min, _, _ = calculate_work_stats(entries)
            worked_hours = round(worked_min / 60, 2)
            emp_data["days"].append({
                "date": day_date.isoformat(),
                "weekday": weekdays[i],
                "worked_hours": worked_hours,
                "break_minutes": break_min
            })
            emp_data["total_worked_hours"] += worked_hours
            emp_data["total_break_minutes"] += break_min
        result.append(emp_data)
    return result

@public_router.get("/api/reports/employee/{employee_id}")
async def employee_detail(employee_id: int, date: str, request: Request, db: AsyncSession = Depends(get_db)):
    session_employee_id = request.session.get("employee_id")
    is_admin = request.session.get("is_admin", False)
    if not is_admin and session_employee_id != employee_id:
        raise HTTPException(403, "You can only view your own reports")
    emp = await crud.get_employee_by_id(db, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    target_date = datetime.strptime(date, "%Y-%m-%d").date()
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())
    entries = await crud.get_time_entries(db, employee_id=employee_id, start_date=start_of_day, end_date=end_of_day)
    entries_list = [{"id": e.id, "timestamp": e.timestamp.isoformat(), "action": e.action} for e in entries]
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
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())
    entries = await crud.get_time_entries(db, employee_id=employee.id, start_date=start_of_day, end_date=end_of_day)
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
        "not_on_break": "🔵 Не в перерыве",
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
async def admin_create_timelog(data: TimeEntryCreateAdmin, db: AsyncSession = Depends(get_db)):
    employee = await crud.get_employee_by_id(db, data.employee_id)
    if not employee:
        raise HTTPException(404, "Employee not found")
    try:
        dt = datetime.fromisoformat(data.timestamp)
    except ValueError:
        raise HTTPException(400, "Invalid timestamp format. Use ISO format.")
    entry = await crud.create_time_entry_admin(db, data.employee_id, data.action, dt, source="admin")
    return {"status": "ok", "entry_id": entry.id}

@public_router.put("/api/admin/timelog/{entry_id}")
async def admin_update_timelog(entry_id: int, data: TimeEntryUpdateAdmin, db: AsyncSession = Depends(get_db)):
    try:
        dt = datetime.fromisoformat(data.timestamp)
    except ValueError:
        raise HTTPException(400, "Invalid timestamp format. Use ISO format.")
    try:
        entry = await crud.update_time_entry(db, entry_id, dt)
    except ValueError:
        raise HTTPException(404, "Entry not found")
    return {"status": "ok", "entry_id": entry.id, "new_timestamp": entry.timestamp.isoformat()}

@public_router.delete("/api/admin/timelog/{entry_id}", status_code=204)
async def admin_delete_timelog(entry_id: int, db: AsyncSession = Depends(get_db)):
    try:
        await crud.delete_time_entry(db, entry_id)
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
    request: Request,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    if not request.session.get("is_admin", False):
        raise HTTPException(403, "Admin access required")
    
    stmt = select(
        models.TimeEntry.id,
        models.TimeEntry.timestamp,
        models.TimeEntry.action,
        models.TimeEntry.source,
        models.Employee.full_name,
        models.Employee.username
    ).join(
        models.Employee, models.TimeEntry.employee_id == models.Employee.id
    ).order_by(desc(models.TimeEntry.timestamp)).limit(limit)
    
    result = await db.execute(stmt)
    rows = result.all()
    
    action_map = {
        "start": "Начало рабочего дня",
        "break_start": "Начало перерыва",
        "break_end": "Конец перерыва",
        "end": "Конец рабочего дня"
    }
    
    entries = []
    for row in rows:
        entries.append({
            "id": row.id,
            "timestamp": row.timestamp.isoformat(),
            "action": action_map.get(row.action, row.action),
            "source": row.source,
            "full_name": row.full_name,
            "username": row.username
        })
    return entries