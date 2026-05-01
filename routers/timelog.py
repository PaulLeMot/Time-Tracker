from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from database import get_db
import models
import schemas
import crud
from datetime import datetime
from datetime import time
from crud import convert_end_start_to_break
from sse import notify_admin_clients, notify_monitor_clients

router = APIRouter(prefix="/api/timelog", tags=["timelog"])

async def get_last_entry(db: AsyncSession, employee_id: int):

    stmt = select(models.TimeEntry).where(
        models.TimeEntry.employee_id == employee_id
    ).order_by(desc(models.TimeEntry.timestamp)).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

def is_action_valid(current_action: str, last_action: str | None) -> bool:
    if last_action is None:
        return current_action == "start"
    
    if last_action == "start":
        return current_action in ("break_start", "end")
    elif last_action == "break_start":
        return current_action == "break_end"
    elif last_action == "break_end":
        return current_action in ("break_start", "end")
    elif last_action == "end":
        return current_action == "start"
    else:
        return False

@router.post("/")
async def create_timelog(entry: schemas.TimeLogCreate, db: AsyncSession = Depends(get_db)):
    employee = await crud.get_employee_by_id(db, entry.user_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    now = datetime.now()
    target_date = now.date()
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())

    if now.time() >= time(22, 0, 0):
        raise HTTPException(400, "Нельзя отмечаться после 22:00")

    last_entry = await get_last_entry(db, entry.user_id)
    last_action = last_entry.action if last_entry else None

    """if last_action == "start" and last_entry:
        time_diff = (now - last_entry.timestamp).total_seconds()
        if time_diff > 12 * 3600:
            last_action = None"""

    if not is_action_valid(entry.action, last_action):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action '{entry.action}' after '{last_action}'. Allowed: {get_allowed_next(last_action)}"
        )

    if entry.action == "end":
        await convert_end_start_to_break(db, entry.user_id, start_of_day, end_of_day)

    db_entry = models.TimeEntry(
        employee_id=entry.user_id,
        action=entry.action,
        timestamp=now,
        source="barcode"
    )
    db.add(db_entry)
    await db.commit()
    await db.refresh(db_entry)
    await notify_admin_clients()
    await notify_monitor_clients()
    return {"status": "ok", "entry_id": db_entry.id}

def get_allowed_next(last_action: str | None) -> list:

    if last_action is None:
        return ["start"]
    transitions = {
        "start": ["break_start", "end"],
        "break_start": ["break_end"],
        "break_end": ["break_start", "end"],
        "end": ["start"]
    }
    return transitions.get(last_action, [])

@router.get("/last/{employee_id}")
async def get_last_action(employee_id: int, db: AsyncSession = Depends(get_db)):
    employee = await crud.get_employee_by_id(db, employee_id)
    if not employee:
        raise HTTPException(404, "Employee not found")
    last_entry = await get_last_entry(db, employee_id)
    return {"last_action": last_entry.action if last_entry else None}