import uuid
from sqlalchemy import select, update, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from datetime import datetime, time, timedelta, date
from models import (
    Employee,
    TimeEntry,
    SystemSetting,
    Notification,
    NotificationType,
    NotificationStatus,
    DealType,
    Client,
    Role,
    Deal,
    DealProduct,
    DealProductStage,
    TaskType,
    Task,
    EmployeeRole,
    DealEmployeeRole,
    IP,
    MP,
    DealHistory,
    DayStatus,
    DayType
)
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


async def update_employee_with_username(db: AsyncSession, employee_id: int, username: str = None, full_name: str = None, is_active: int = None) -> Employee:
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


# ---------- Автозакрытие смен ----------
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
    
    workday_date = (now - timedelta(days=1)).date()
    
    for emp in employees:
        last_entry = await get_last_entry(db, emp.id)
        if not last_entry:
            continue
        if last_entry.action == "end":
            continue
        
        start_of_day = datetime.combine(now.date(), time(5, 0, 0))
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
        await db.flush()
        forced_end = True
        await db.commit()
        await notify_admin_clients()
        await notify_monitor_clients()
        
        if forced_end and admin:
            notif_stmt = select(Notification).where(
                Notification.employee_id == emp.id,
                Notification.type == NotificationType.WARNING,
                Notification.message == "Не был завершен рабочий день",
                Notification.extra_data['workday_date'].astext == workday_date.isoformat()
            )
            existing = await db.execute(notif_stmt)
            existing_notif = existing.scalar_one_or_none()
            if existing_notif:
                extra = existing_notif.extra_data or {}
                extra["auto_end_entry_id"] = end_entry.id
                existing_notif.extra_data = dict(extra)
                await db.commit()
                await notify_employee(emp.id)
            else:
                notification = Notification(
                    employee_id=emp.id,
                    admin_id=admin.id,
                    type=NotificationType.WARNING,
                    message="Не был завершен рабочий день",
                    status=NotificationStatus.SENT,
                    source="auto",
                    extra_data={
                        "workday_date": workday_date.isoformat(),
                        "auto_end_entry_id": end_entry.id
                    }
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


# ========== ДОПОЛНЕНИЯ ДЛЯ ПЕСОЧНИЦЫ ==========

# ---------- Справочники ----------
async def get_deal_types(db: AsyncSession):
    result = await db.execute(select(DealType))
    return result.scalars().all()


async def get_clients(db: AsyncSession):
    result = await db.execute(select(Client))
    return result.scalars().all()


async def get_roles(db: AsyncSession):
    result = await db.execute(select(Role))
    return result.scalars().all()


# ---------- Сделки ----------
async def create_deal(
    db: AsyncSession,
    title: str,
    deal_type_id: int,
    client_id: int,
    planned_date: date,
    created_by: int,
    products: list  # list of {"name": str, "tech_card": list or None}
) -> Deal:
    """
    Создаёт сделку с товарами. Товары хранятся в DealProduct.
    products: [{"name": "Товар 1", "tech_card": ["этап1", "этап2"]}, ...]
    """
    deal = Deal(
        title=title,
        deal_type_id=deal_type_id,
        client_id=client_id,
        planned_date=planned_date,
        status="draft",
        created_by=created_by,
        updated_by=created_by
    )
    db.add(deal)
    await db.flush()

    for prod in products:
        deal_product = DealProduct(
            deal_id=deal.id,
            name=prod["name"],
            tech_card=prod.get("tech_card")  # может быть None
        )
        db.add(deal_product)

    await db.commit()
    await db.refresh(deal)
    return deal


async def get_deal_by_id(db: AsyncSession, deal_id: int) -> Deal | None:
    stmt = select(Deal).where(Deal.id == deal_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_deal_with_details(db: AsyncSession, deal_id: int):
    stmt = (
        select(Deal)
        .options(
            joinedload(Deal.deal_type),
            joinedload(Deal.client),
            joinedload(Deal.creator),
            joinedload(Deal.updater),
            joinedload(Deal.deal_products)  # загружаем товары
        )
        .where(Deal.id == deal_id)
    )
    result = await db.execute(stmt)
    return result.unique().scalar_one_or_none()


async def get_deals(db: AsyncSession, status: str | None = None, skip: int = 0, limit: int = 100):
    stmt = select(Deal).order_by(Deal.created_at.desc())
    if status:
        stmt = stmt.where(Deal.status == status)
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


async def update_deal(db: AsyncSession, deal_id: int, **kwargs):
    stmt = update(Deal).where(Deal.id == deal_id).values(**kwargs, updated_at=datetime.now()).returning(Deal)
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()


async def delete_deal(db: AsyncSession, deal_id: int):
    stmt = delete(Deal).where(Deal.id == deal_id)
    await db.execute(stmt)
    await db.commit()


# ---------- Если нужны этапы (опционально) ----------
async def add_stage_to_product(db: AsyncSession, deal_product_id: int, task_id: int, sequence: int):
    stage = DealProductStage(
        deal_product_id=deal_product_id,
        task_id=task_id,
        sequence=sequence,
        status="pending"
    )
    db.add(stage)
    await db.commit()
    await db.refresh(stage)
    return stage


async def get_stages_for_product(db: AsyncSession, deal_product_id: int):
    stmt = select(DealProductStage).where(DealProductStage.deal_product_id == deal_product_id).order_by(DealProductStage.sequence)
    result = await db.execute(stmt)
    return result.scalars().all()


# ---------- Управление этапами (если нужны) ----------
async def update_task(db: AsyncSession, task_stage_id: int, **kwargs):
    stmt = update(DealProductStage).where(DealProductStage.id == task_stage_id).values(**kwargs).returning(DealProductStage)
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()


async def get_task_by_id(db: AsyncSession, task_stage_id: int):
    stmt = select(DealProductStage).where(DealProductStage.id == task_stage_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_employee_tasks(db: AsyncSession, employee_id: int, status: str | None = None):
    stmt = (
        select(DealProductStage)
        .options(
            joinedload(DealProductStage.deal_product).joinedload(DealProduct.deal),
            joinedload(DealProductStage.task)
        )
        .where(DealProductStage.assigned_employee_id == employee_id)
    )
    if status:
        stmt = stmt.where(DealProductStage.status == status)
    stmt = stmt.order_by(DealProductStage.sequence)
    result = await db.execute(stmt)
    return result.unique().scalars().all()


# ---------- Логистика ----------
async def update_deal_logistics(db: AsyncSession, deal_id: int, **kwargs):
    stmt = update(Deal).where(Deal.id == deal_id).values(**kwargs, updated_at=datetime.now()).returning(Deal)
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()


# ---------- Назначения ролей ----------
async def assign_employee_role_global(db: AsyncSession, employee_id: int, role_id: int):
    employee_role = EmployeeRole(employee_id=employee_id, role_id=role_id)
    db.add(employee_role)
    await db.commit()
    return employee_role


async def assign_employee_role_in_deal(db: AsyncSession, deal_id: int, employee_id: int, role_id: int):
    deal_role = DealEmployeeRole(deal_id=deal_id, employee_id=employee_id, role_id=role_id)
    db.add(deal_role)
    await db.commit()
    return deal_role


async def get_employees_with_role(db: AsyncSession, role_id: int, deal_id: int | None = None):
    if deal_id:
        stmt = select(DealEmployeeRole.employee_id).where(
            DealEmployeeRole.deal_id == deal_id,
            DealEmployeeRole.role_id == role_id
        )
        result = await db.execute(stmt)
        emp_ids = [row[0] for row in result.all()]
        if emp_ids:
            stmt_emp = select(Employee).where(Employee.id.in_(emp_ids), Employee.is_active == 1)
            result_emp = await db.execute(stmt_emp)
            return result_emp.scalars().all()
    stmt = select(Employee).join(EmployeeRole).where(
        EmployeeRole.role_id == role_id,
        Employee.is_active == 1
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# ---------- Task Types ----------
async def get_task_types(db: AsyncSession):
    result = await db.execute(select(TaskType))
    return result.scalars().all()


async def create_task_type(db: AsyncSession, name: str):
    task_type = TaskType(name=name)
    db.add(task_type)
    await db.commit()
    await db.refresh(task_type)
    return task_type


async def delete_task_type(db: AsyncSession, type_id: int):
    stmt = delete(TaskType).where(TaskType.id == type_id)
    await db.execute(stmt)
    await db.commit()


# ---------- Tasks ----------
async def get_tasks(db: AsyncSession):
    stmt = select(Task).options(joinedload(Task.type))
    result = await db.execute(stmt)
    return result.unique().scalars().all()


async def create_task(db: AsyncSession, name: str, type_id: int):
    task = Task(name=name, type_id=type_id)
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def delete_task(db: AsyncSession, task_id: int):
    stmt = delete(Task).where(Task.id == task_id)
    await db.execute(stmt)
    await db.commit()


# ---------- IP ----------
async def get_ips(db: AsyncSession):
    result = await db.execute(select(IP).order_by(IP.name))
    return result.scalars().all()

async def create_ip(db: AsyncSession, name: str):
    ip = IP(name=name)
    db.add(ip)
    await db.commit()
    await db.refresh(ip)
    return ip

async def delete_ip(db: AsyncSession, ip_id: int):
    stmt = delete(IP).where(IP.id == ip_id)
    await db.execute(stmt)
    await db.commit()


# ---------- MP ----------
async def get_mps(db: AsyncSession):
    result = await db.execute(select(MP).order_by(MP.name))
    return result.scalars().all()

async def create_mp(db: AsyncSession, name: str):
    mp = MP(name=name)
    db.add(mp)
    await db.commit()
    await db.refresh(mp)
    return mp

async def delete_mp(db: AsyncSession, mp_id: int):
    stmt = delete(MP).where(MP.id == mp_id)
    await db.execute(stmt)
    await db.commit()


# ---------- Deal Types ----------
async def delete_deal_type(db: AsyncSession, type_id: int):
    stmt = delete(DealType).where(DealType.id == type_id)
    await db.execute(stmt)
    await db.commit()

async def create_deal_type(db: AsyncSession, name: str):
    deal_type = DealType(name=name, code=name.upper())
    db.add(deal_type)
    await db.commit()
    await db.refresh(deal_type)
    return deal_type

async def update_deal_type(db: AsyncSession, type_id: int, name: str):
    stmt = update(DealType).where(DealType.id == type_id).values(name=name, code=name.upper()).returning(DealType)
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()