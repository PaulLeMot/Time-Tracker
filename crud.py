import uuid
from sqlalchemy import select, update, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from datetime import datetime, time, timedelta, date
from typing import Optional, List, Dict
from schemas import DealProductItem
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
    DealTypeTask,
    TaskExecution,
    TaskExecutionStatus,
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
    # Время автозакрытия – сегодня в 5:00
    auto_time = datetime.combine(now.date(), time(5, 0, 0))
    # Рабочий день, который закрываем – предыдущий день (с 5:00 вчера до 5:00 сегодня)
    workday_date = (now - timedelta(days=1)).date()
    workday_start = datetime.combine(workday_date, time(5, 0, 0))
    workday_end = workday_start + timedelta(days=1)  # сегодня в 5:00

    employees = await get_employees(db, active_only=True)

    admin_stmt = select(Employee).where(Employee.is_admin == 1).limit(1)
    admin_result = await db.execute(admin_stmt)
    admin = admin_result.scalar_one_or_none()

    for emp in employees:
        # Получаем последнюю запись за этот рабочий день
        stmt = (
            select(TimeEntry)
            .where(
                TimeEntry.employee_id == emp.id,
                TimeEntry.timestamp >= workday_start,
                TimeEntry.timestamp < workday_end
            )
            .order_by(TimeEntry.timestamp.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        last_entry = result.scalar_one_or_none()

        # Если записей за день нет – значит сотрудник не работал, пропускаем
        if not last_entry:
            continue

        # Если последняя запись за день уже "end" – всё закрыто
        if last_entry.action == "end":
            continue

        # Иначе – смена не завершена, нужно закрыть
        forced_end = False

        # Если последняя запись – начало перерыва, нужно сначала закрыть перерыв
        if last_entry.action == "break_start":
            # Добавляем break_end за секунду до автозакрытия
            break_time = workday_end - timedelta(seconds=1)
            break_end_entry = TimeEntry(
                employee_id=emp.id,
                action="break_end",
                timestamp=break_time,
                source="auto"
            )
            db.add(break_end_entry)

        # Создаём запись окончания рабочего дня в 5:00
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

        # Создаём уведомление о незавершённом дне
        if forced_end and admin:
            # Проверяем, нет ли уже такого уведомления за этот день
            notif_stmt = select(Notification).where(
                Notification.employee_id == emp.id,
                Notification.type == NotificationType.WARNING,
                Notification.message == "Не был завершен рабочий день",
                Notification.extra_data.op('->>')('workday_date') == workday_date.isoformat()
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
    ip_id: Optional[int] = None,
    mp_id: Optional[int] = None,
    products: Optional[List[DealProductItem]] = None
) -> Deal:
    new_deal = Deal(
        title=title,
        deal_type_id=deal_type_id,
        ip_id=ip_id,
        mp_id=mp_id
    )
    db.add(new_deal)
    await db.flush()

    if products:
        await add_products_to_deal(db, new_deal.id, products)
    else:
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
    # 1. Находим все уведомления о задачах, связанные с этой сделкой
    stmt_notifications = select(Notification).where(
        Notification.type == NotificationType.TASK_ASSIGNMENT,
        Notification.extra_data.op('->>')('deal_id') == str(deal_id)
    )
    result = await db.execute(stmt_notifications)
    notifications = result.scalars().all()

    # 2. Удаляем связанные TaskExecution и сами уведомления
    for notif in notifications:
        # Удаляем TaskExecution
        te_stmt = select(TaskExecution).where(TaskExecution.notification_id == notif.id)
        te_result = await db.execute(te_stmt)
        task_exec = te_result.scalar_one_or_none()
        if task_exec:
            await db.delete(task_exec)
        # Удаляем Explanation (если есть)
        exp_stmt = select(Explanation).where(Explanation.notification_id == notif.id)
        exp_result = await db.execute(exp_stmt)
        explanation = exp_result.scalar_one_or_none()
        if explanation:
            await db.delete(explanation)
        # Удаляем само уведомление
        await db.delete(notif)

    # 3. Удаляем сделку (каскадно удалятся deal_products через cascade)
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

async def get_or_create_product_type(
    db: AsyncSession,
    name: str,
    full_name: Optional[str] = None
) -> ProductType:
    """Найти товар по имени, если нет – создать."""
    stmt = select(ProductType).where(ProductType.name == name)
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()
    if product:
        return product
    return await create_product_type(db, name=name, full_name=full_name)

async def add_products_to_deal(
    db: AsyncSession,
    deal_id: int,
    products: List[DealProductItem]
) -> None:
    """Привязать товары к сделке (создавая товары при необходимости)."""
    for item in products:
        product = await get_or_create_product_type(db, item.name, item.full_name)
        deal_product = DealProductType(
            deal_id=deal_id,
            product_id=product.id,
            quantity=item.quantity
        )
        db.add(deal_product)
    await db.commit()

async def get_deal_type_tasks(db: AsyncSession) -> dict:
    """Возвращает словарь: {deal_type_id: {task_id: is_enabled}}"""
    stmt = select(DealTypeTask)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    data = {}
    for row in rows:
        if row.deal_type_id not in data:
            data[row.deal_type_id] = {}
        data[row.deal_type_id][row.task_id] = row.is_enabled
    return data

async def set_deal_type_tasks(db: AsyncSession, data: dict):
    """
    data: {deal_type_id: [task_ids, ...]} — список задач, которые должны быть включены (True).
    Все остальные задачи для этого типа будут сохранены как False.
    """
    # Получаем все задачи (чтобы знать, какие существуют)
    all_tasks = await get_tasks(db)  # предполагаем, что get_tasks возвращает список Task
    all_task_ids = [task.id for task in all_tasks]

    for deal_type_id, enabled_task_ids in data.items():
        # Удаляем старые записи для этого типа
        await db.execute(delete(DealTypeTask).where(DealTypeTask.deal_type_id == deal_type_id))
        
        # Создаём записи для ВСЕХ задач
        for task_id in all_task_ids:
            is_enabled = task_id in enabled_task_ids
            db.add(DealTypeTask(
                deal_type_id=deal_type_id,
                task_id=task_id,
                is_enabled=is_enabled
            ))
    
    await db.commit()

async def get_deal_with_products_and_tech_cards(db: AsyncSession, deal_id: int):
    """Загружает сделку с товарами, типами товаров, техкартами и задачами."""
    stmt = select(Deal).where(Deal.id == deal_id).options(
        joinedload(Deal.deal_products).joinedload(DealProductType.product_type).options(
            joinedload(ProductType.tech_card).options(
                selectinload(TechCard.tech_card_tasks).selectinload(TechCardTask.task)
            )
        )
    )
    result = await db.execute(stmt)
    return result.unique().scalar_one_or_none()

async def get_task_roles(db: AsyncSession, task_ids: List[int]) -> Dict[int, List[int]]:
    """Возвращает словарь {task_id: [role_id, ...]} для переданных task_ids."""
    stmt = select(RoleTask).where(RoleTask.task_id.in_(task_ids))
    result = await db.execute(stmt)
    rows = result.scalars().all()
    task_roles = {}
    for rt in rows:
        task_roles.setdefault(rt.task_id, []).append(rt.role_id)
    return task_roles

async def get_employees_for_roles(db: AsyncSession, role_ids: List[int]) -> Dict[int, List[int]]:
    """Возвращает словарь {role_id: [employee_id, ...]} для переданных role_ids."""
    stmt = select(EmployeeRole).where(EmployeeRole.role_id.in_(role_ids))
    result = await db.execute(stmt)
    rows = result.scalars().all()
    role_employees = {}
    for er in rows:
        role_employees.setdefault(er.role_id, []).append(er.employee_id)
    return role_employees

from sqlalchemy import cast, Integer
from sqlalchemy.orm import selectinload
from models import Notification, Employee, Task, Deal, NotificationType

async def get_task_assignment_notifications(db: AsyncSession, skip: int = 0, limit: int = 100):
    stmt = select(Notification).where(Notification.type == NotificationType.TASK_ASSIGNMENT).order_by(Notification.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    notifications = result.scalars().all()
    
    if not notifications:
        return []
    
    employee_ids = set()
    task_ids = set()
    deal_ids = set()
    for n in notifications:
        if n.employee_id:
            employee_ids.add(n.employee_id)
        if n.extra_data:
            task_ids.add(n.extra_data.get('task_id'))
            deal_ids.add(n.extra_data.get('deal_id'))
    
    employees = {}
    if employee_ids:
        stmt_emp = select(Employee).where(Employee.id.in_(employee_ids))
        emp_result = await db.execute(stmt_emp)
        for e in emp_result.scalars():
            employees[e.id] = e.full_name
    
    tasks = {}
    if task_ids:
        stmt_task = select(Task).where(Task.id.in_(task_ids))
        task_result = await db.execute(stmt_task)
        for t in task_result.scalars():
            tasks[t.id] = t.name
    
    deals = {}
    if deal_ids:
        stmt_deal = select(Deal).where(Deal.id.in_(deal_ids))
        deal_result = await db.execute(stmt_deal)
        for d in deal_result.scalars():
            deals[d.id] = d.title
    
    output = []
    for n in notifications:
        task_id = n.extra_data.get('task_id') if n.extra_data else None
        deal_id = n.extra_data.get('deal_id') if n.extra_data else None
        output.append({
            "id": n.id,
            "employee_name": employees.get(n.employee_id),
            "task_name": tasks.get(task_id) if task_id else None,
            "deal_title": deals.get(deal_id) if deal_id else None,
            "message": n.message,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        })
    return output

# ========== TaskExecution CRUD ==========

async def get_task_execution_by_notification(db: AsyncSession, notification_id: int) -> Optional[TaskExecution]:
    stmt = select(TaskExecution).where(TaskExecution.notification_id == notification_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def update_task_execution_status(
    db: AsyncSession,
    notification_id: int,
    status: TaskExecutionStatus,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None
) -> TaskExecution:
    task_exec = await get_task_execution_by_notification(db, notification_id)
    if not task_exec:
        raise ValueError("Task execution not found")
    task_exec.status = status
    if started_at is not None:
        task_exec.started_at = started_at
    if completed_at is not None:
        task_exec.completed_at = completed_at
    await db.commit()
    await db.refresh(task_exec)
    return task_exec
# ========================================================
#   ЗАВЕРШЕНИЕ ЗАДАЧ (БРАК И РАСПРЕДЕЛЕНИЕ)
# ========================================================

from sqlalchemy import select, delete, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from models import TaskCompletionData, TaskProductionDistribution, DealProductType, ProductType, TechCardTask, Task
from typing import List, Optional, Dict, Any
import logging


async def get_task_completion_data(
    db: AsyncSession,
    deal_id: int,
    task_id: int,
    product_type_id: int
) -> Optional[TaskCompletionData]:
    """Получить запись о завершении задачи для конкретного типа товара."""
    stmt = select(TaskCompletionData).where(
        TaskCompletionData.deal_id == deal_id,
        TaskCompletionData.task_id == task_id,
        TaskCompletionData.product_type_id == product_type_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_task_completion_with_distributions(
    db: AsyncSession,
    deal_id: int,
    task_id: int,
    product_type_id: int
) -> Optional[Dict[str, Any]]:
    """
    Получить полные данные о завершении задачи для конкретного типа товара с распределениями.
    (Оптимизировано: 3 отдельных запроса заменены на 1 основной с жадной загрузкой)
    """
    stmt = (
        select(TaskCompletionData)
        .where(
            TaskCompletionData.deal_id == deal_id,
            TaskCompletionData.task_id == task_id,
            TaskCompletionData.product_type_id == product_type_id
        )
        .options(
            # Жадно подгружаем тип товара (убирает db.get(ProductType))
            selectinload(TaskCompletionData.product_type),
            # Жадно подгружаем распределения И их сотрудников (убирает отдельный select)
            selectinload(TaskCompletionData.distributions).selectinload(TaskProductionDistribution.employee)
        )
    )
    
    result = await db.execute(stmt)
    # unique() обязателен при загрузке коллекций через selectinload/joinedload
    data = result.unique().scalar_one_or_none()
    
    if not data:
        return None
        
    return {
        "product_type_id": product_type_id,
        "product_type_name": data.product_type.name if data.product_type else None,
        "defect_quantity": data.defect_quantity,
        "defect_comment": data.defect_comment,
        "distributions": [
            {
                "employee_id": d.employee_id,
                # Добавил проверку на наличие сотрудника на случай каскадного удаления
                "employee_name": d.employee.full_name if d.employee else None, 
                "quantity": d.quantity
            }
            for d in data.distributions
        ]
    }


async def get_task_total_quantity(
    db: AsyncSession,
    deal_id: int,
    task_id: int,
    product_type_id: int
) -> int:
    """
    Вычислить общее количество товаров конкретного типа, назначенных на задачу в рамках сделки.
    Учитывается только если задача присутствует в техкарте этого типа товара.
    """
    stmt = select(
        func.sum(DealProductType.quantity)
    ).join(
        ProductType, ProductType.id == DealProductType.product_id
    ).join(
        TechCardTask, TechCardTask.tech_card_id == ProductType.tech_card_id
    ).where(
        DealProductType.deal_id == deal_id,
        TechCardTask.task_id == task_id,
        ProductType.id == product_type_id
    )
    result = await db.execute(stmt)
    total = result.scalar() or 0
    return int(total)


async def create_or_update_task_completion(
    db: AsyncSession,
    deal_id: int,
    task_id: int,
    product_type_id: int,
    defect_quantity: int = 0,
    defect_comment: Optional[str] = None,
    distributions: Optional[List[Dict[str, int]]] = None  # [{"employee_id": int, "quantity": int}, ...]
) -> TaskCompletionData:
    """
    Создаёт или обновляет запись о завершении задачи для конкретного типа товара и её распределения.
    distributions – список словарей с полями employee_id и quantity.
    Сумма quantity по всем распределениям должна совпадать с общим количеством товаров данного типа в задаче.
    Если distributions не переданы – все существующие распределения удаляются.
    """
    # Проверяем, что сумма распределений равна общему количеству товаров для этого типа
    total_quantity = await get_task_total_quantity(db, deal_id, task_id, product_type_id)
    if distributions:
        sum_dist = sum(d.get("quantity", 0) for d in distributions)
        if sum_dist != total_quantity:
            raise ValueError(
                f"Сумма распределений ({sum_dist}) не равна общему количеству товаров типа {product_type_id} ({total_quantity})"
            )
    
    # Ищем существующую запись
    existing = await get_task_completion_data(db, deal_id, task_id, product_type_id)
    
    if existing:
        # Обновляем существующую
        existing.defect_quantity = defect_quantity
        existing.defect_comment = defect_comment
        # Удаляем старые распределения
        await db.execute(
            delete(TaskProductionDistribution).where(
                TaskProductionDistribution.task_completion_id == existing.id
            )
        )
        await db.flush()
    else:
        # Создаём новую
        existing = TaskCompletionData(
            deal_id=deal_id,
            task_id=task_id,
            product_type_id=product_type_id,
            defect_quantity=defect_quantity,
            defect_comment=defect_comment
        )
        db.add(existing)
        await db.flush()  # чтобы получить id
    
    # Добавляем новые распределения
    if distributions:
        for d in distributions:
            dist = TaskProductionDistribution(
                task_completion_id=existing.id,
                employee_id=d["employee_id"],
                quantity=d["quantity"]
            )
            db.add(dist)
    
    await db.commit()
    await db.refresh(existing)
    return existing


async def delete_task_completion(
    db: AsyncSession,
    deal_id: int,
    task_id: int,
    product_type_id: int
) -> bool:
    """Удалить все данные о завершении задачи для конкретного типа товара (включая распределения)."""
    data = await get_task_completion_data(db, deal_id, task_id, product_type_id)
    if not data:
        return False
    await db.delete(data)
    await db.commit()
    return True


async def get_all_task_completions_for_deal(
    db: AsyncSession,
    deal_id: int
) -> List[Dict[str, Any]]:
    """
    Получить данные о завершении для всех задач и типов товаров сделки.
    (Исправлена проблема N+1 за счет жадной загрузки / eager loading)
    """
    # 1. Формируем запрос с жадной загрузкой связанных таблиц
    stmt = (
        select(TaskCompletionData)
        .where(TaskCompletionData.deal_id == deal_id)
        .options(
            # Подгружаем тип товара
            selectinload(TaskCompletionData.product_type),
            # Подгружаем распределения И внутри них сразу подгружаем сотрудников
            selectinload(TaskCompletionData.distributions).selectinload(TaskProductionDistribution.employee)
        )
    )
    
    result = await db.execute(stmt)
    # unique() нужен, чтобы SQLAlchemy корректно дедуплицировал строки при загрузке коллекций
    rows = result.unique().scalars().all()
    
    output = []
    for row in rows:
        # 2. Теперь все данные уже в памяти (в объектах SQLAlchemy). 
        # Никаких запросов к БД внутри цикла больше нет!
        output.append({
            "task_id": row.task_id,
            "product_type_id": row.product_type_id,
            "product_type_name": row.product_type.name if row.product_type else None,
            "defect_quantity": row.defect_quantity,
            "defect_comment": row.defect_comment,
            "distributions": [
                {
                    "employee_id": d.employee_id,
                    "employee_name": d.employee.full_name if d.employee else None,
                    "quantity": d.quantity
                }
                for d in row.distributions
            ]
        })
    return output


async def check_completion_data_exists_for_deal(
    db: AsyncSession,
    deal_id: int
) -> bool:
    """Проверить, есть ли хоть одна запись о завершении для сделки."""
    stmt = select(func.count()).select_from(TaskCompletionData).where(
        TaskCompletionData.deal_id == deal_id
    )
    result = await db.execute(stmt)
    count = result.scalar()
    return count > 0

async def is_employee_task_executor(
    db: AsyncSession,
    employee_id: int,
    task_id: int,
    deal_id: int
) -> bool:
    """Проверяет, является ли сотрудник исполнителем задачи (основным или соисполнителем)."""
    stmt = select(Notification).where(
        Notification.employee_id == employee_id,
        Notification.type == NotificationType.TASK_ASSIGNMENT,
        Notification.status == NotificationStatus.SENT,
        Notification.extra_data.op('->>')('deal_id') == str(deal_id),
        Notification.extra_data.op('->>')('task_id') == str(task_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None