from fastapi import APIRouter, Depends, HTTPException, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import barcode
from barcode.writer import ImageWriter
from io import BytesIO
from typing import List, Optional
from database import get_db
import crud
from fastapi.responses import FileResponse
from datetime import datetime
class EmployeeCreate(BaseModel):
    full_name: str

class EmployeeResponse(BaseModel):
    id: int
    full_name: str
    qr_code_secret: str
    is_active: int

class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    is_active: Optional[int] = None

class TimeEntryCreateAdmin(BaseModel):
    employee_id: int
    action: str
    timestamp: str

class TimeEntryUpdateAdmin(BaseModel):
    timestamp: str

page_router = APIRouter(tags=["pages"])
router = APIRouter(prefix="/api/employees", tags=["employees"])
public_router = APIRouter(tags=["public"])

@router.get("/", response_model=List[EmployeeResponse])
async def list_employees(active_only: bool = True, db: AsyncSession = Depends(get_db)):
    employees = await crud.get_employees(db, active_only=active_only)
    return employees

@router.post("/", response_model=EmployeeResponse, status_code=201)
async def create_employee(emp_data: EmployeeCreate, db: AsyncSession = Depends(get_db)):
    employee = await crud.create_employee(db, full_name=emp_data.full_name)
    return employee

@router.get("/{employee_id}/qr")
async def get_employee_qr(employee_id: int, action: str = "start", db: AsyncSession = Depends(get_db)):
    employee = await crud.get_employee_by_id(db, employee_id)
    if not employee:
        raise HTTPException(404, detail="Employee not found")
    barcode_data = f"{employee_id}:{action}"
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
    updated = await crud.update_employee(db, employee_id, full_name=update_data.full_name, is_active=update_data.is_active)
    return updated

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
    return FileResponse("templates/admin.html")

@public_router.get("/api/reports/daily")
async def daily_report(date: str, db: AsyncSession = Depends(get_db)):
    employees = await crud.get_employees(db, active_only=True)
    target_date = datetime.strptime(date, "%Y-%m-%d").date()
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())
    result = []
    for emp in employees:
        entries = await crud.get_time_entries(db, employee_id=emp.id, start_date=start_of_day, end_date=end_of_day)
        worked, breaks, start_time, end_time = calculate_work_stats(entries)
        result.append({
            "employee_id": emp.id,
            "full_name": emp.full_name,
            "start_time": start_time,
            "end_time": end_time,
            "break_minutes": breaks,
            "worked_hours": round(worked / 60, 2)
        })
    return result

@public_router.get("/api/reports/employee/{employee_id}")
async def employee_detail(employee_id: int, date: str, db: AsyncSession = Depends(get_db)):
    emp = await crud.get_employee_by_id(db, employee_id)
    if not emp:
        raise HTTPException(404, "Employee not found")
    target_date = datetime.strptime(date, "%Y-%m-%d").date()
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())
    entries = await crud.get_time_entries(db, employee_id=employee_id, start_date=start_of_day, end_date=end_of_day)
    entries_list = [{"timestamp": e.timestamp.isoformat(), "action": e.action} for e in entries]
    worked, breaks, _, _ = calculate_work_stats(entries)
    return {
        "employee_id": employee_id,
        "full_name": emp.full_name,
        "date": date,
        "entries": entries_list,
        "worked_hours": round(worked / 60, 2),
        "break_minutes": breaks
    }

@public_router.post("/api/admin/timelog", status_code=201)
async def admin_create_timelog(data: TimeEntryCreateAdmin, db: AsyncSession = Depends(get_db)):
    employee = await crud.get_employee_by_id(db, data.employee_id)
    if not employee:
        raise HTTPException(404, "Employee not found")
    try:
        dt = datetime.fromisoformat(data.timestamp.replace('Z', '+00:00'))
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
    except ValueError:
        raise HTTPException(400, "Invalid timestamp format. Use ISO format.")
    entry = await crud.create_time_entry_admin(db, data.employee_id, data.action, dt, source="admin")
    return {"status": "ok", "entry_id": entry.id}

@public_router.put("/api/admin/timelog/{entry_id}")
async def admin_update_timelog(entry_id: int, data: TimeEntryUpdateAdmin, db: AsyncSession = Depends(get_db)):
    try:
        dt = datetime.fromisoformat(data.timestamp.replace('Z', '+00:00'))
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
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
                total_work_sec += (ts - last_start).total_seconds()
                last_start = None
        elif action == "break_start":
            if in_shift and not in_break:
                in_break = True
                last_break_start = ts
        elif action == "break_end":
            if in_break:
                in_break = False
                total_break_sec += (ts - last_break_start).total_seconds()
    worked_min = total_work_sec // 60
    break_min = total_break_sec // 60
    start_str = start_time.isoformat() if start_time else None
    end_str = end_time.isoformat() if end_time else None
    return worked_min, break_min, start_str, end_str