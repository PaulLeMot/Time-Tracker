from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
import models
import schemas
from datetime import datetime

router = APIRouter(prefix="/api/timelog", tags=["timelog"])

@router.post("/")
async def create_timelog(entry: schemas.TimeLogCreate, db: AsyncSession = Depends(get_db)):
    # Пример: просто сохраняем запись
    db_entry = models.TimeEntry(
        employee_id=entry.user_id,
        action=entry.action,
        timestamp=datetime.utcnow(),
        source="qr"
    )
    db.add(db_entry)
    await db.commit()
    await db.refresh(db_entry)
    return {"status": "ok", "entry_id": db_entry.id}