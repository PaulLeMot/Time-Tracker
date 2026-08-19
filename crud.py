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
    Explanation,
    Product,
    DayStatus,
    DayType,
    DealType,
    Role,
    Deal,
    DealProductType,
    ProductType,\
    TechCard,
    TechCardTask,
    TaskType,
    Task,
    EmployeeRole,
    IP,
    MP,
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

# для сделок, задач и прочего:

async def get_deal_by_id(db: AsyncSession, deal_id: int):
    stmt = select(Deal).where(Deal.id == deal_id).options(
        joinedload(Deal.deal_type),
        joinedload(Deal.ip),
        joinedload(Deal.mp),
        joinedload(Deal.deal_products).joinedload(DealProductType.product_type)
    )
    result = await db.execute(stmt)
    return result.unique().scalar_one_or_none()

async def get_deals(db: AsyncSession, skip: int = 0, limit: int = 100) -> list[Deal]:
    stmt = select(Deal).options(
        joinedload(Deal.deal_type),
        joinedload(Deal.ip),
        joinedload(Deal.mp)
    ).order_by(Deal.id.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return result.unique().scalars().all()

async def create_deal(
    db: AsyncSession,
    title: str,
    deal_type_id: int,
    ip_id: int = None,
    mp_id: int = None
) -> Deal:
    new_deal = Deal(
        title=title,
        deal_type_id=deal_type_id,
        ip_id=ip_id,
        mp_id=mp_id
    )
    db.add(new_deal)
    await db.commit()
    await db.refresh(new_deal)
    return new_deal

async def update_deal(
    db: AsyncSession, deal_id: int, title: str = None, deal_type_id: int = None
    ) -> Deal:
    stmt = update(Deal).where(Deal.id == deal_id)
    values = {}
    if title is not None:
        values["title"] = title
    if deal_type_id is not None:
        values["deal_type_id"] = deal_type_id
    if not values:
        return await get_deal_by_id(db, deal_id)
    stmt = stmt.values(**values).returning(Deal)
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()

async def delete_deal(db: AsyncSession, deal_id: int) -> None:
    stmt = delete(Deal).where(Deal.id == deal_id)
    await db.execute(stmt)
    await db.commit()

async def get_product_type(db: AsyncSession, product_type_id: int) -> ProductType | None:
    stmt = select(ProductType).where(ProductType.id == product_type_id).options(joinedload(ProductType.tech_card))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def get_product_types(
    db: AsyncSession,
    limit: int = 100,
    offset: int = 0,
    name_filter: str = None
) -> list[ProductType]:
    stmt = select(ProductType).options(joinedload(ProductType.tech_card))
    if name_filter:
        stmt = stmt.where(ProductType.name.ilike(f"%{name_filter}%"))
    stmt = stmt.order_by(ProductType.id).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.unique().scalars().all()

async def create_product_type(
    db: AsyncSession,
    name: str,
    full_name: str = None,
    tech_card_id: int = None
) -> ProductType:
    new_product_type = ProductType(
        name=name,
        full_name=full_name,
        tech_card_id=tech_card_id
    )
    db.add(new_product_type)
    await db.commit()
    await db.refresh(new_product_type)
    return new_product_type

async def update_product_type(
    db: AsyncSession,
    product_type_id: int,
    name: str = None,
    full_name: str = None,
    tech_card_id: int = None
) -> ProductType:
    existing = await get_product_type(db, product_type_id)
    if not existing:
        raise ValueError("ProductType not found")

    values = {}
    if name is not None:
        values["name"] = name
    if full_name is not None:
        values["full_name"] = full_name
    if tech_card_id is not None:
        values["tech_card_id"] = tech_card_id
    if not values:
        return existing

    stmt = update(ProductType).where(ProductType.id == product_type_id).values(**values).returning(ProductType)
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()

async def delete_product_type(db: AsyncSession, product_type_id: int) -> None:
    stmt = delete(ProductType).where(ProductType.id == product_type_id)
    await db.execute(stmt)
    await db.commit()

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from models import TechCard, ProductType, TechCardTask, Task


# ---------- Получение по ID ----------
async def get_tech_card(db: AsyncSession, tech_card_id: int) -> TechCard | None:
    stmt = select(TechCard).where(TechCard.id == tech_card_id).options(
        selectinload(TechCard.tech_card_tasks).selectinload(TechCardTask.task)
    )
    result = await db.execute(stmt)
    return result.unique().scalar_one_or_none()


# ---------- Список с пагинацией и поиском ----------
async def get_tech_cards(
    db: AsyncSession,
    limit: int = 100,
    offset: int = 0,
    name_filter: str = None
) -> list[TechCard]:
    stmt = select(TechCard).options(
        selectinload(TechCard.tech_card_tasks).selectinload(TechCardTask.task)
    )
    if name_filter:
        stmt = stmt.where(TechCard.name.ilike(f"%{name_filter}%"))
    stmt = stmt.order_by(TechCard.id).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.unique().scalars().all()


# ---------- Создание ----------
async def create_tech_card(db: AsyncSession, name: str) -> TechCard:
    new_tech_card = TechCard(name=name)
    db.add(new_tech_card)
    await db.commit()
    await db.refresh(new_tech_card)
    return new_tech_card


# ---------- Обновление ----------
async def update_tech_card(db: AsyncSession, tech_card_id: int, name: str = None) -> TechCard:
    existing = await get_tech_card(db, tech_card_id)
    if not existing:
        raise ValueError("TechCard not found")
    if name is None:
        return existing

    values = {"name": name}
    stmt = update(TechCard).where(TechCard.id == tech_card_id).values(**values).returning(TechCard)
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()


# ---------- Удаление ----------
async def delete_tech_card(db: AsyncSession, tech_card_id: int) -> None:
    # Удаляем все связанные TechCardTask вручную (если нет каскада в БД)
    await db.execute(delete(TechCardTask).where(TechCardTask.tech_card_id == tech_card_id))
    # Обнуляем tech_card_id у всех ProductType, которые ссылаются на эту техкарту
    await db.execute(
        update(ProductType)
        .where(ProductType.tech_card_id == tech_card_id)
        .values(tech_card_id=None)
    )
    stmt = delete(TechCard).where(TechCard.id == tech_card_id)
    await db.execute(stmt)
    await db.commit()

# ---------- Получить все продукты техкарты ----------
async def get_products_by_tech_card(db: AsyncSession, tech_card_id: int) -> list[ProductType]:
    stmt = select(ProductType).where(ProductType.tech_card_id == tech_card_id)
    result = await db.execute(stmt)
    return result.scalars().all()


# ---------- Добавить продукт к техкарте ----------
async def add_product_to_tech_card(db: AsyncSession, product_type_id: int, tech_card_id: int) -> ProductType:
    product = await get_product_type(db, product_type_id)  # предполагаем, что такая функция уже есть
    if not product:
        raise ValueError("ProductType not found")
    product.tech_card_id = tech_card_id
    await db.commit()
    await db.refresh(product)
    return product


# ---------- Удалить продукт из техкарты (отвязать) ----------
async def remove_product_from_tech_card(db: AsyncSession, product_type_id: int) -> ProductType:
    product = await get_product_type(db, product_type_id)
    if not product:
        raise ValueError("ProductType not found")
    product.tech_card_id = None
    await db.commit()
    await db.refresh(product)
    return product

# ---------- Получить все задачи техкарты с порядком ----------
async def get_tasks_by_tech_card(db: AsyncSession, tech_card_id: int) -> list[TechCardTask]:
    stmt = (
        select(TechCardTask)
        .where(TechCardTask.tech_card_id == tech_card_id)
        .order_by(TechCardTask.sequence)
    )
    result = await db.execute(stmt)
    return result.scalars().all()

# Или с подгрузкой данных задачи:
async def get_tasks_with_details_by_tech_card(db: AsyncSession, tech_card_id: int) -> list[TechCardTask]:
    stmt = (
        select(TechCardTask)
        .where(TechCardTask.tech_card_id == tech_card_id)
        .options(joinedload(TechCardTask.task).joinedload(Task.task_type))
        .order_by(TechCardTask.sequence)
    )
    result = await db.execute(stmt)
    return result.unique().scalars().all()


# ---------- Добавить задачу к техкарте с указанием последовательности ----------
async def add_task_to_tech_card(
    db: AsyncSession,
    tech_card_id: int,
    task_id: int,
    sequence: int = None
) -> TechCardTask:
    # Если sequence не указан, добавляем в конец
    if sequence is None:
        max_seq_stmt = select(func.max(TechCardTask.sequence)).where(TechCardTask.tech_card_id == tech_card_id)
        max_seq_result = await db.execute(max_seq_stmt)
        max_seq = max_seq_result.scalar() or 0
        sequence = max_seq + 1
    else:
        # Если указан, сдвигаем существующие
        stmt = select(TechCardTask).where(
            TechCardTask.tech_card_id == tech_card_id,
            TechCardTask.task_id == task_id
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise ValueError("Task already exists in this tech card")
        if sequence < 1:
            raise ValueError("Sequence must be >= 1")
        await db.execute(
            update(TechCardTask)
            .where(
                TechCardTask.tech_card_id == tech_card_id,
                TechCardTask.sequence >= sequence
            )
            .values(sequence=TechCardTask.sequence + 1)
        )

    new_link = TechCardTask(
        tech_card_id=tech_card_id,
        task_id=task_id,
        sequence=sequence
    )
    db.add(new_link)
    await db.commit()
    await db.refresh(new_link)
    return new_link

# ---------- Удалить задачу из техкарты ----------
async def remove_task_from_tech_card(
    db: AsyncSession,
    tech_card_id: int,
    task_id: int
) -> None:
    # 1. Находим удаляемую связь
    stmt = select(TechCardTask).where(
        TechCardTask.tech_card_id == tech_card_id,
        TechCardTask.task_id == task_id
    )
    result = await db.execute(stmt)
    link = result.scalar_one_or_none()
    if not link:
        raise ValueError("Task not found in this tech card")

    deleted_sequence = link.sequence

    # 2. Удаляем связь
    await db.delete(link)

    # 3. Перенумеровываем оставшиеся задачи (уменьшаем sequence на 1 для тех, у кого sequence > deleted_sequence)
    await db.execute(
        update(TechCardTask)
        .where(
            TechCardTask.tech_card_id == tech_card_id,
            TechCardTask.sequence > deleted_sequence
        )
        .values(sequence=TechCardTask.sequence - 1)
    )

    await db.commit()


# ---------- Изменить порядок (sequence) конкретной задачи ----------
async def update_task_sequence(
    db: AsyncSession,
    tech_card_id: int,
    task_id: int,
    new_sequence: int
) -> TechCardTask:
    link = await db.execute(
        select(TechCardTask).where(
            TechCardTask.tech_card_id == tech_card_id,
            TechCardTask.task_id == task_id
        )
    )
    link = link.scalar_one_or_none()
    if not link:
        raise ValueError("Task not found in this tech card")
    link.sequence = new_sequence
    await db.commit()
    await db.refresh(link)
    return link


# ---------- Массовое обновление порядка (перестановка) ----------
async def reorder_tech_card_tasks(
    db: AsyncSession,
    tech_card_id: int,
    ordered_task_ids: list[int]
) -> list[TechCardTask]:
    # Удаляем все старые связи для этой техкарты
    await db.execute(delete(TechCardTask).where(TechCardTask.tech_card_id == tech_card_id))
    # Создаём новые с последовательными номерами
    for idx, task_id in enumerate(ordered_task_ids, start=1):
        db.add(TechCardTask(tech_card_id=tech_card_id, task_id=task_id, sequence=idx))
    await db.commit()
    # Возвращаем обновлённый список
    return await get_tasks_by_tech_card(db, tech_card_id)

async def reorder_tech_card_sequences(db: AsyncSession, tech_card_id: int) -> None:
    stmt = (
        select(TechCardTask)
        .where(TechCardTask.tech_card_id == tech_card_id)
        .order_by(TechCardTask.sequence)
    )
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    for idx, link in enumerate(tasks, start=1):
        if link.sequence != idx:
            link.sequence = idx

async def delete_task(db: AsyncSession, task_id: int) -> None:
    # 1. Получаем уникальные ID техкарт, где присутствует задача
    stmt = select(TechCardTask.tech_card_id).where(TechCardTask.task_id == task_id).distinct()
    result = await db.execute(stmt)
    tech_card_ids = result.scalars().all()

    # 2. Удаляем все связи для этой задачи (из всех техкарт)
    await db.execute(delete(TechCardTask).where(TechCardTask.task_id == task_id))

    # 3. Пересчитываем порядок для каждой техкарты, где были удалены записи
    for tech_card_id in tech_card_ids:
        await reorder_tech_card_sequences(db, tech_card_id)

    # 4. Удаляем саму задачу
    # Проверяем, существует ли задача (опционально)
    task = await get_task(db, task_id)  # предполагаем, что функция get_task есть
    if not task:
        raise ValueError("Task not found")
    await db.delete(task)

    # 5. Фиксируем все изменения одной транзакцией
    await db.commit()

# ---------- Вставить задачу в техкарту на конкретную позицию (с пересчётом порядка) ----------
async def insert_task_to_tech_card(
    db: AsyncSession,
    tech_card_id: int,
    task_id: int,
    sequence: int
) -> TechCardTask:
    # Проверяем, не существует ли уже связь
    stmt = select(TechCardTask).where(
        TechCardTask.tech_card_id == tech_card_id,
        TechCardTask.task_id == task_id
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise ValueError("Task already exists in this tech card")

    # Убеждаемся, что sequence >= 1
    if sequence < 1:
        raise ValueError("Sequence must be >= 1")

    # Сдвигаем все существующие задачи с sequence >= new_sequence на 1 вверх
    await db.execute(
        update(TechCardTask)
        .where(
            TechCardTask.tech_card_id == tech_card_id,
            TechCardTask.sequence >= sequence
        )
        .values(sequence=TechCardTask.sequence + 1)
    )

    # Добавляем новую задачу
    new_link = TechCardTask(
        tech_card_id=tech_card_id,
        task_id=task_id,
        sequence=sequence
    )
    db.add(new_link)
    await db.commit()
    await db.refresh(new_link)
    return new_link

# ---------- Получение типа задачи по ID ----------
async def get_task_type(db: AsyncSession, task_type_id: int) -> TaskType | None:
    stmt = select(TaskType).where(TaskType.id == task_type_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ---------- Список типов задач с пагинацией и поиском ----------
async def get_task_types(
    db: AsyncSession,
    limit: int = 100,
    offset: int = 0,
    name_filter: str = None
) -> list[TaskType]:
    stmt = select(TaskType)
    if name_filter:
        stmt = stmt.where(TaskType.name.ilike(f"%{name_filter}%"))
    stmt = stmt.order_by(TaskType.id).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return result.scalars().all()


# ---------- Создание типа задачи ----------
async def create_task_type(db: AsyncSession, name: str) -> TaskType:
    new_type = TaskType(name=name)
    db.add(new_type)
    await db.commit()
    await db.refresh(new_type)
    return new_type


# ---------- Обновление типа задачи ----------
async def update_task_type(
    db: AsyncSession,
    task_type_id: int,
    name: str = None
) -> TaskType:
    existing = await get_task_type(db, task_type_id)
    if not existing:
        raise ValueError("TaskType not found")
    if name is None:
        return existing

    values = {"name": name}
    stmt = update(TaskType).where(TaskType.id == task_type_id).values(**values).returning(TaskType)
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()


# ---------- Удаление типа задачи ----------
async def delete_task_type(db: AsyncSession, task_type_id: int) -> None:
    # Проверяем, есть ли задачи с этим типом
    stmt = select(Task).where(Task.task_type_id == task_type_id)
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    if tasks:
        raise ValueError(f"Cannot delete task type: {len(tasks)} tasks still use it")

    stmt = delete(TaskType).where(TaskType.id == task_type_id)
    await db.execute(stmt)
    await db.commit()

# ---------- Получение задачи по ID ----------
async def get_task(db: AsyncSession, task_id: int) -> Task | None:
    stmt = select(Task).where(Task.id == task_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ---------- Список задач с пагинацией, поиском и фильтром по типу ----------
async def get_tasks(
    db: AsyncSession,
    limit: int = 100,
    offset: int = 0,
    name_filter: str = None,
    task_type_id: int = None
) -> list[Task]:
    stmt = select(Task).options(joinedload(Task.task_type))  # <-- добавляем
    if name_filter:
        stmt = stmt.where(Task.name.ilike(f"%{name_filter}%"))
    if task_type_id is not None:
        stmt = stmt.where(Task.task_type_id == task_type_id)
    stmt = stmt.order_by(Task.id).offset(offset).limit(limit)
    result = await db.execute(stmt)
    # unique() нужен, чтобы избежать дублирования из-за joinedload (хотя в данном случае один к одному, но добавляем на всякий случай)
    return result.unique().scalars().all()


# ---------- Создание задачи ----------
async def create_task(
    db: AsyncSession,
    name: str,
    task_type_id: int = None
) -> Task:
    new_task = Task(name=name, task_type_id=task_type_id)
    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)
    return new_task


# ---------- Обновление задачи (название и/или тип) ----------
async def update_task(
    db: AsyncSession,
    task_id: int,
    name: str = None,
    task_type_id: int = None
) -> Task:
    existing = await get_task(db, task_id)
    if not existing:
        raise ValueError("Task not found")

    values = {}
    if name is not None:
        values["name"] = name
    if task_type_id is not None:
        values["task_type_id"] = task_type_id
    if not values:
        return existing

    stmt = update(Task).where(Task.id == task_id).values(**values).returning(Task)
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()

# ---------- Получение всех IP ----------
async def get_all_ips(db: AsyncSession) -> list[IP]:
    stmt = select(IP).order_by(IP.id)
    result = await db.execute(stmt)
    return result.scalars().all()


# ---------- Получение IP по ID ----------
async def get_ip_by_id(db: AsyncSession, ip_id: int) -> IP | None:
    stmt = select(IP).where(IP.id == ip_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ---------- Получение IP по имени ----------
async def get_ip_by_name(db: AsyncSession, name: str) -> IP | None:
    stmt = select(IP).where(IP.name == name)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ---------- Создание IP ----------
async def create_ip(db: AsyncSession, name: str) -> IP:
    # Проверка на существование с таким же именем (опционально)
    existing = await get_ip_by_name(db, name)
    if existing:
        raise ValueError(f"IP with name '{name}' already exists")
    new_ip = IP(name=name)
    db.add(new_ip)
    await db.commit()
    await db.refresh(new_ip)
    return new_ip


# ---------- Обновление IP ----------
async def update_ip(db: AsyncSession, ip_id: int, new_name: str) -> IP:
    ip = await get_ip_by_id(db, ip_id)
    if not ip:
        raise ValueError("IP not found")
    # Проверяем, не занято ли новое имя другим IP
    if new_name != ip.name:
        existing = await get_ip_by_name(db, new_name)
        if existing and existing.id != ip_id:
            raise ValueError(f"IP with name '{new_name}' already exists")
        ip.name = new_name
        await db.commit()
        await db.refresh(ip)
    return ip


# ---------- Удаление IP ----------
async def delete_ip(db: AsyncSession, ip_id: int) -> None:
    ip = await get_ip_by_id(db, ip_id)
    if not ip:
        raise ValueError("IP not found")
    await db.delete(ip)
    await db.commit()

# ---------- Получение всех MP ----------
async def get_all_mps(db: AsyncSession) -> list[MP]:
    stmt = select(MP).order_by(MP.id)
    result = await db.execute(stmt)
    return result.scalars().all()


# ---------- Получение MP по ID ----------
async def get_mp_by_id(db: AsyncSession, mp_id: int) -> MP | None:
    stmt = select(MP).where(MP.id == mp_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ---------- Получение MP по имени ----------
async def get_mp_by_name(db: AsyncSession, name: str) -> MP | None:
    stmt = select(MP).where(MP.name == name)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ---------- Создание MP ----------
async def create_mp(db: AsyncSession, name: str) -> MP:
    existing = await get_mp_by_name(db, name)
    if existing:
        raise ValueError(f"MP with name '{name}' already exists")
    new_mp = MP(name=name)
    db.add(new_mp)
    await db.commit()
    await db.refresh(new_mp)
    return new_mp


# ---------- Обновление MP ----------
async def update_mp(db: AsyncSession, mp_id: int, new_name: str) -> MP:
    mp = await get_mp_by_id(db, mp_id)
    if not mp:
        raise ValueError("MP not found")
    if new_name != mp.name:
        existing = await get_mp_by_name(db, new_name)
        if existing and existing.id != mp_id:
            raise ValueError(f"MP with name '{new_name}' already exists")
        mp.name = new_name
        await db.commit()
        await db.refresh(mp)
    return mp


# ---------- Удаление MP ----------
async def delete_mp(db: AsyncSession, mp_id: int) -> None:
    mp = await get_mp_by_id(db, mp_id)
    if not mp:
        raise ValueError("MP not found")
    await db.delete(mp)
    await db.commit()

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from models import DealType, Deal


# ---------- Получение всех типов сделок ----------
async def get_deal_types(db: AsyncSession) -> list[DealType]:
    stmt = select(DealType).order_by(DealType.id)
    result = await db.execute(stmt)
    return result.scalars().all()


# ---------- Получение типа сделки по ID ----------
async def get_deal_type(db: AsyncSession, deal_type_id: int) -> DealType | None:
    stmt = select(DealType).where(DealType.id == deal_type_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ---------- Создание типа сделки ----------
async def create_deal_type(db: AsyncSession, name: str) -> DealType:
    # Проверка на существование с таким же именем (опционально)
    stmt = select(DealType).where(DealType.name == name)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise ValueError(f"DealType with name '{name}' already exists")

    new_type = DealType(name=name)
    db.add(new_type)
    await db.commit()
    await db.refresh(new_type)
    return new_type


# ---------- Обновление типа сделки ----------
async def update_deal_type(
    db: AsyncSession,
    deal_type_id: int,
    name: str
) -> DealType:
    existing = await get_deal_type(db, deal_type_id)
    if not existing:
        raise ValueError("DealType not found")

    # Если имя меняется, проверяем уникальность
    if name != existing.name:
        stmt = select(DealType).where(DealType.name == name)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise ValueError(f"DealType with name '{name}' already exists")

    existing.name = name
    await db.commit()
    await db.refresh(existing)
    return existing


# ---------- Удаление типа сделки ----------
async def delete_deal_type(db: AsyncSession, deal_type_id: int) -> None:
    # Проверяем, есть ли сделки с этим типом
    stmt = select(Deal).where(Deal.deal_type_id == deal_type_id)
    result = await db.execute(stmt)
    deals = result.scalars().all()
    if deals:
        raise ValueError(f"Cannot delete deal type: {len(deals)} deals still use it")

    deal_type = await get_deal_type(db, deal_type_id)
    if not deal_type:
        raise ValueError("DealType not found")

    await db.delete(deal_type)
    await db.commit()

# ============================ РОЛИ ============================

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from models import Role, RoleTask, Task, EmployeeRole


# ---------- Получение всех ролей (с подгрузкой задач и сотрудников) ----------
async def get_roles(db: AsyncSession) -> list[Role]:
    stmt = select(Role).options(
        selectinload(Role.role_tasks).selectinload(RoleTask.task),
        selectinload(Role.employee_roles).selectinload(EmployeeRole.employee)
    ).order_by(Role.id)
    result = await db.execute(stmt)
    return result.unique().scalars().all()


# ---------- Получение роли по ID (с задачами и сотрудниками) ----------
async def get_role(db: AsyncSession, role_id: int) -> Role | None:
    stmt = select(Role).where(Role.id == role_id).options(
        selectinload(Role.role_tasks).selectinload(RoleTask.task),
        selectinload(Role.employee_roles).selectinload(EmployeeRole.employee)
    )
    result = await db.execute(stmt)
    return result.unique().scalar_one_or_none()


# ---------- Создание роли (с возможностью сразу добавить задачи) ----------
async def create_role(
    db: AsyncSession,
    name: str,
    description: str = None,
    task_ids: list[int] = None,
    allow_multiple: bool = True
) -> Role:
    new_role = Role(name=name, description=description)
    db.add(new_role)
    await db.flush()  # чтобы получить new_role.id

    if task_ids:
        for task_id in task_ids:
            db.add(RoleTask(role_id=new_role.id, task_id=task_id))

    await db.commit()
    await db.refresh(new_role)
    return new_role


# ---------- Обновление роли (название, описание, задачи) ----------
async def update_role(
    db: AsyncSession,
    role_id: int,
    name: str = None,
    description: str = None,
    task_ids: list[int] = None,
    allow_multiple: bool = None
) -> Role:
    role = await get_role(db, role_id)
    if not role:
        raise ValueError("Role not found")

    if name is not None:
        role.name = name
    if description is not None:
        role.description = description
    if allow_multiple is not None:
        role.allow_multiple = allow_multiple
    # Если передан список task_ids, заменяем все задачи
    if task_ids is not None:
        # Удаляем все старые связи
        await db.execute(delete(RoleTask).where(RoleTask.role_id == role_id))
        # Добавляем новые
        for task_id in task_ids:
            db.add(RoleTask(role_id=role_id, task_id=task_id))

    await db.commit()
    await db.refresh(role)
    return role


# ---------- Удаление роли ----------
async def delete_role(db: AsyncSession, role_id: int) -> None:
    role = await get_role(db, role_id)
    if not role:
        raise ValueError("Role not found")
    await db.delete(role)
    await db.commit()

# ---------- Добавить сотрудника в роль ----------
async def add_employee_to_role(db: AsyncSession, role_id: int, employee_id: int) -> EmployeeRole:
    # Проверяем существование роли
    role = await get_role(db, role_id)
    if not role:
        raise ValueError("Role not found")

    # Если множественное назначение запрещено – проверяем, не занята ли роль
    if not role.allow_multiple:
        stmt = select(EmployeeRole).where(EmployeeRole.role_id == role_id)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            raise ValueError("Эта должность уже назначена другому сотруднику (множественное назначение запрещено)")

    # Проверяем, не назначен ли уже этот сотрудник на эту роль
    stmt = select(EmployeeRole).where(
        EmployeeRole.role_id == role_id,
        EmployeeRole.employee_id == employee_id
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise ValueError("Employee already assigned to this role")

    link = EmployeeRole(role_id=role_id, employee_id=employee_id)
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link


# ---------- Удалить сотрудника из роли ----------
async def remove_employee_from_role(db: AsyncSession, role_id: int, employee_id: int) -> None:
    stmt = delete(EmployeeRole).where(
        EmployeeRole.role_id == role_id,
        EmployeeRole.employee_id == employee_id
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise ValueError("Employee not found in this role")
    await db.commit()

# ---------- Управление задачами роли (добавление/удаление отдельных задач) ----------

async def add_task_to_role(db: AsyncSession, role_id: int, task_id: int) -> RoleTask:
    # Проверяем, существует ли уже такая связь
    stmt = select(RoleTask).where(
        RoleTask.role_id == role_id,
        RoleTask.task_id == task_id
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise ValueError("Task already assigned to this role")

    link = RoleTask(role_id=role_id, task_id=task_id)
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link


async def remove_task_from_role(db: AsyncSession, role_id: int, task_id: int) -> None:
    stmt = delete(RoleTask).where(
        RoleTask.role_id == role_id,
        RoleTask.task_id == task_id
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise ValueError("Task not found in this role")
    await db.commit()


# ---------- Получение списка задач, привязанных к роли ----------
async def get_tasks_for_role(db: AsyncSession, role_id: int) -> list[Task]:
    stmt = select(Task).join(RoleTask, RoleTask.task_id == Task.id).where(RoleTask.role_id == role_id)
    result = await db.execute(stmt)
    return result.scalars().all()


# ---------- Заменить все задачи роли новым списком (если не хотите делать через update_role) ----------
async def set_role_tasks(db: AsyncSession, role_id: int, task_ids: list[int]) -> list[Task]:
    # Удаляем все старые связи
    await db.execute(delete(RoleTask).where(RoleTask.role_id == role_id))
    # Добавляем новые
    for task_id in task_ids:
        db.add(RoleTask(role_id=role_id, task_id=task_id))
    await db.commit()
    # Возвращаем обновлённый список задач
    return await get_tasks_for_role(db, role_id)

async def get_roles_for_employee(db: AsyncSession, employee_id: int) -> list[Role]:
    stmt = select(Role).join(EmployeeRole, EmployeeRole.role_id == Role.id).where(
        EmployeeRole.employee_id == employee_id
    ).options(
        selectinload(Role.role_tasks).selectinload(RoleTask.task),
        selectinload(Role.employee_roles).selectinload(EmployeeRole.employee)
    )
    result = await db.execute(stmt)
    return result.unique().scalars().all()