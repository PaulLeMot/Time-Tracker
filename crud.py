import uuid
from sqlalchemy import select, update, delete, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, time, timedelta
from models import Employee, TimeEntry, SystemSetting
import secrets
import string
from sse import notify_admin_clients, notify_monitor_clients

async def get_employees(db: AsyncSession, active_only: bool = True):

    stmt = select(Employee)
    if active_only:
        stmt = stmt.where(Employee.is_active == 1)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_employee_by_id(db: AsyncSession, employee_id: int):

    result = await db.execute(select(Employee).where(Employee.id == employee_id))
    return result.scalar_one_or_none()

async def get_employee_by_barcode_secret(db: AsyncSession, barcode_secret: str):

    result = await db.execute(select(Employee).where(Employee.barcode_secret == barcode_secret))
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

def generate_random_password(length: int = 6) -> str:
    return ''.join(secrets.choice(string.digits) for _ in range(length))

async def set_employee_password(db: AsyncSession, employee_id: int, plain_password: str) -> Employee:
    employee = await get_employee_by_id(db, employee_id)
    if not employee:
        raise ValueError("Employee not found")
    employee.password = plain_password
    await db.commit()
    await db.refresh(employee)
    return employee

async def get_employee_by_full_name(db: AsyncSession, full_name: str):
    stmt = select(Employee).where(Employee.full_name == full_name)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def create_employee(db: AsyncSession, username: str, full_name: str) -> Employee:
    barcode_secret = str(uuid.uuid4()).replace('-', '')[:16]
    new_employee = Employee(
        full_name=full_name,
        username=username,
        barcode_secret=barcode_secret,
        is_active=1
    )
    db.add(new_employee)
    await db.commit()
    await db.refresh(new_employee)
    return new_employee

async def get_employee_by_username(db: AsyncSession, username: str):
    stmt = select(Employee).where(Employee.username == username)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def update_employee(db: AsyncSession, employee_id: int, username: str = None, full_name: str = None, is_active: int = None) -> Employee:
    stmt = update(Employee).where(Employee.id == employee_id)
    updates = {}
    if username is not None:
        updates['username'] = username
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

from sqlalchemy import select
from models import TimeEntry, Employee
from datetime import datetime

async def auto_close_shifts(db: AsyncSession):
    from sse import notify_employee
    from models import Notification, NotificationType, NotificationStatus
    now = datetime.now()
    auto_time = datetime.combine(now.date(), time(5, 0, 0))
    break_time = auto_time - timedelta(seconds=1)
    employees = await get_employees(db, active_only=True)
    admin_stmt = select(Employee).where(Employee.is_admin == 1).limit(1)
    admin_result = await db.execute(admin_stmt)
    admin = admin_result.scalar_one_or_none()
    for emp in employees:
        last_entry = await get_last_entry(db, emp.id)
        if not last_entry:
            continue
        if last_entry.action == "end":
            continue
        start_of_day = datetime.combine(now.date(), datetime.min.time())
        stmt = select(TimeEntry).where(
            TimeEntry.employee_id == emp.id,
            TimeEntry.action == "end",
            TimeEntry.source == "auto",
            TimeEntry.timestamp >= start_of_day
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            continue
        forced_end = False
        if last_entry.action == "break_start":
            break_end_entry = TimeEntry(
                employee_id=emp.id,
                action="break_end",
                timestamp=break_time,
                source="auto"
            )
            db.add(break_end_entry)
        end_entry = TimeEntry(
            employee_id=emp.id,
            action="end",
            timestamp=auto_time,
            source="auto"
        )
        db.add(end_entry)
        forced_end = True
        await db.commit()
        await notify_admin_clients()
        await notify_monitor_clients()
        if forced_end and admin:
            notif_stmt = select(Notification).where(
                Notification.employee_id == emp.id,
                Notification.type == NotificationType.WARNING,
                Notification.created_at >= start_of_day
            )
            existing = await db.execute(notif_stmt)
            if not existing.scalar_one_or_none():
                notification = Notification(
                    employee_id=emp.id,
                    admin_id=admin.id,
                    type=NotificationType.WARNING,
                    message="Не был завершен рабочий день",
                    status=NotificationStatus.SENT,
                    source="auto"
                )
                db.add(notification)
                await db.commit()
                await notify_employee(emp.id)

async def get_last_entry(db: AsyncSession, employee_id: int):
    stmt = select(TimeEntry).where(
        TimeEntry.employee_id == employee_id
    ).order_by(desc(TimeEntry.timestamp)).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def convert_end_start_to_break(
    db: AsyncSession,
    employee_id: int,
    start_of_day: datetime,
    end_of_day: datetime
) -> bool:

    stmt = select(TimeEntry).where(
        TimeEntry.employee_id == employee_id,
        TimeEntry.timestamp >= start_of_day,
        TimeEntry.timestamp <= end_of_day
    ).order_by(TimeEntry.timestamp)
    result = await db.execute(stmt)
    entries = result.scalars().all()

    for i in range(len(entries) - 1):
        if entries[i].action == "end" and entries[i+1].action == "start":
            entries[i].action = "break_start"
            entries[i+1].action = "break_end"
            entries[i].source = "auto"
            entries[i+1].source = "auto"
            await db.commit()
            await notify_admin_clients()
            await notify_monitor_clients()
            return True
    return False

async def get_rounding_interval(db: AsyncSession) -> int:
    stmt = select(SystemSetting).where(SystemSetting.key == "rounding_interval_minutes")
    result = await db.execute(stmt)
    setting = result.scalar_one_or_none()
    return int(setting.value) if setting else 15

async def set_rounding_interval(db: AsyncSession, minutes: int):
    stmt = update(SystemSetting).where(SystemSetting.key == "rounding_interval_minutes").values(value=str(minutes))
    await db.execute(stmt)
    await db.commit()

def floor_round_minutes(minutes: int, interval: int) -> int:
    return (minutes // interval) * interval

async def is_late(db: AsyncSession, employee: Employee, start_time: datetime) -> bool:
    if not employee.schedule_data:
        return False
    weekday = start_time.weekday()
    day_key = str(weekday)
    if day_key not in employee.schedule_data:
        return False
    scheduled_start_str = employee.schedule_data[day_key].get("start")
    if not scheduled_start_str:
        return False
    try:
        scheduled_start_time = datetime.strptime(scheduled_start_str, "%H:%M").time()
    except ValueError:
        return False
    scheduled_start = datetime.combine(start_time.date(), scheduled_start_time)
    late_minutes = (start_time - scheduled_start).total_seconds() / 60.0
    return late_minutes > 5

def get_workday_date(dt: datetime) -> datetime.date:
    if dt.time() >= time(5, 0, 0):
        return dt.date()
    else:
        return dt.date() - timedelta(days=1)