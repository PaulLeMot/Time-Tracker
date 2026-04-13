import uuid
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from models import Employee, TimeEntry

async def create_employee(db: AsyncSession, full_name: str) -> Employee:
    qr_secret = str(uuid.uuid4()).replace('-', '')[:16]
    new_employee = Employee(
        full_name=full_name,
        qr_code_secret=qr_secret,
        is_active=1
    )
    db.add(new_employee)
    await db.commit()
    await db.refresh(new_employee)
    return new_employee

async def get_employees(db: AsyncSession, active_only: bool = True):

    stmt = select(Employee)
    if active_only:
        stmt = stmt.where(Employee.is_active == 1)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_employee_by_id(db: AsyncSession, employee_id: int):

    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    return result.scalar_one_or_none()

async def get_employee_by_qr_secret(db: AsyncSession, qr_secret: str):

    result = await db.execute(select(Employee).where(Employee.qr_code_secret == qr_secret))
    return result.scalar_one_or_none()

async def update_employee(db: AsyncSession, employee_id: int, full_name: str = None, is_active: int = None) -> Employee:

    stmt = update(Employee).where(Employee.id == employee_id)
    updates = {}
    if full_name is not None:
        updates['full_name'] = full_name
    if is_active is not None:
        updates['is_active'] = is_active
    if not updates:
        return await get_employee_by_id(db, employee_id)
    stmt = stmt.values(**updates).returning(Employee)
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()

async def deactivate_employee(db: AsyncSession, employee_id: int) -> Employee:

    return await update_employee(db, employee_id, is_active=0)

async def delete_employee(db: AsyncSession, employee_id: int):

    stmt = delete(Employee).where(Employee.id == employee_id)
    await db.execute(stmt)
    await db.commit()

async def get_time_entries(
    db: AsyncSession,
    employee_id: int = None,
    start_date: datetime = None,
    end_date: datetime = None
):
    stmt = select(TimeEntry)
    if employee_id is not None:
        stmt = stmt.where(TimeEntry.employee_id == employee_id)
    if start_date is not None:
        stmt = stmt.where(TimeEntry.timestamp >= start_date)
    if end_date is not None:
        stmt = stmt.where(TimeEntry.timestamp <= end_date)
    stmt = stmt.order_by(TimeEntry.timestamp)
    result = await db.execute(stmt)
    return result.scalars().all()

async def create_time_entry_admin(
    db: AsyncSession,
    employee_id: int,
    action: str,
    timestamp: datetime,
    source: str = "admin"
) -> TimeEntry:

    new_entry = TimeEntry(
        employee_id=employee_id,
        action=action,
        timestamp=timestamp,
        source=source
    )
    db.add(new_entry)
    await db.commit()
    await db.refresh(new_entry)
    return new_entry

async def update_time_entry(
    db: AsyncSession,
    entry_id: int,
    new_timestamp: datetime
) -> TimeEntry:

    stmt = select(TimeEntry).where(TimeEntry.id == entry_id)
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()
    if not entry:
        raise ValueError("Entry not found")
    entry.timestamp = new_timestamp
    await db.commit()
    await db.refresh(entry)
    return entry

async def delete_time_entry(
    db: AsyncSession,
    entry_id: int
) -> None:

    stmt = delete(TimeEntry).where(TimeEntry.id == entry_id)
    await db.execute(stmt)
    await db.commit()