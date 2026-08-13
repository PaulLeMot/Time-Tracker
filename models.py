import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text, UniqueConstraint, Date
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import relationship
from enum import Enum
from database import Base

# ========================== ENUMS ==========================

class NotificationType(str, enum.Enum):
    REPRIMAND = "reprimand"
    WARNING = "warning"
    COMMENDATION = "commendation"
    PERFORMANCE_REVIEW = "performance_review"

class NotificationStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    REJECTED = "rejected"

class DayType(str, Enum):
    WORK = "WORK"
    OFF = "OFF"
    VACATION = "VACATION"
    SICK = "SICK"

class DealStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class StageStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class LogisticsStatus(str, enum.Enum):
    PENDING = "pending"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"

class DealTypeCode(str, enum.Enum):
    FBS = "FBS"
    FBP = "FBP"
    FSK = "FSK"

class ClientCode(str, enum.Enum):
    WB = "WB"
    OZ = "OZ"

class IPCode(str, enum.Enum):
    KTV = "KTV"
    KPD = "KPD"
    REG = "REG"
    SIA = "SIA"

# ========================== СУЩЕСТВУЮЩИЕ МОДЕЛИ ==========================

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    username = Column(String, unique=True, nullable=False)
    barcode_secret = Column(String, unique=True, nullable=False)
    is_active = Column(Integer, default=1)
    password = Column(String, nullable=True)
    is_admin = Column(Integer, default=0)
    is_monitor = Column(Integer, default=0)
    schedule_data = Column(JSON, nullable=True)

    deals_created = relationship("Deal", foreign_keys="Deal.created_by", back_populates="creator")
    deals_updated = relationship("Deal", foreign_keys="Deal.updated_by", back_populates="updater")
    assigned_tasks = relationship("DealProductStage", foreign_keys="DealProductStage.assigned_employee_id", back_populates="assigned_employee")
    employee_roles = relationship("EmployeeRole", back_populates="employee", cascade="all, delete-orphan")
    deal_employee_roles = relationship("DealEmployeeRole", back_populates="employee", cascade="all, delete-orphan")
    notifications = relationship("Notification", foreign_keys="Notification.employee_id", back_populates="employee")
    admin_notifications = relationship("Notification", foreign_keys="Notification.admin_id", back_populates="admin")


class TimeEntry(Base):
    __tablename__ = "time_entries"
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, index=True)
    action = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    source = Column(String, default="barcode")


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key = Column(String(100), primary_key=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    admin_id = Column(Integer, ForeignKey("employees.id"), nullable=False)

    type = Column(
        SAEnum(
            NotificationType,
            name="notificationtype",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    message = Column(Text, nullable=False)

    status = Column(
        SAEnum(
            NotificationStatus,
            name="notificationstatus",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        default=NotificationStatus.DRAFT,
    )

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    source = Column(String(20), default="admin")
    extra_data = Column(JSON, nullable=True)

    deal_product_stage_id = Column(Integer, ForeignKey("deal_product_stages.id"), nullable=True)
    task_type = Column(String(20), default="assignment")

    employee = relationship("Employee", foreign_keys=[employee_id], back_populates="notifications")
    admin = relationship("Employee", foreign_keys=[admin_id], back_populates="admin_notifications")
    deal_stage = relationship("DealProductStage", back_populates="notifications")


class Explanation(Base):
    __tablename__ = "explanations"
    id = Column(Integer, primary_key=True)
    notification_id = Column(Integer, ForeignKey("notifications.id"), unique=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    explanation_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now)


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=True)
    product_type = Column(String, nullable=True)
    fandom = Column(String, nullable=True)
    name = Column(String, nullable=False)
    tech_card = Column(Text, nullable=True)
    default_stages = Column(JSON, nullable=True)


class DayStatus(Base):
    __tablename__ = "day_status"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    date = Column(Date, nullable=False)

    day_type = Column(
        SAEnum(
            DayType,
            name="daytype",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=DayType.OFF,
    )

    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    __table_args__ = (UniqueConstraint('employee_id', 'date', name='uix_employee_date'),)


# ========================== НОВЫЕ МОДЕЛИ (ПЕСОЧНИЦА) ==========================

class DealType(Base):
    __tablename__ = "deal_types"
    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, nullable=False)
    name = Column(String(50), nullable=False)

    deals = relationship("Deal", back_populates="deal_type")


class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True)
    code = Column(
        SAEnum(ClientCode, values_callable=lambda e: [v.value for v in e]),
        unique=True,
        nullable=False,
    )
    name = Column(String(50), nullable=False)

    deals = relationship("Deal", back_populates="client")


class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text)

    employee_roles = relationship("EmployeeRole", back_populates="role", cascade="all, delete-orphan")
    deal_employee_roles = relationship("DealEmployeeRole", back_populates="role", cascade="all, delete-orphan")
    assigned_tasks = relationship("DealProductStage", back_populates="assigned_role")


class TaskType(Base):
    __tablename__ = "task_types"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)

    tasks = relationship("Task", back_populates="type", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    type_id = Column(Integer, ForeignKey("task_types.id"), nullable=False)

    type = relationship("TaskType", back_populates="tasks")
    deal_product_stages = relationship("DealProductStage", back_populates="task")


class Deal(Base):
    __tablename__ = "deals"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    deal_type_id = Column(Integer, ForeignKey("deal_types.id"))
    client_id = Column(Integer, ForeignKey("clients.id"))
    planned_date = Column(Date, nullable=False)
    status = Column(
        SAEnum(DealStatus, values_callable=lambda e: [v.value for v in e]),
        default=DealStatus.DRAFT,
    )
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    created_by = Column(Integer, ForeignKey("employees.id"))
    updated_by = Column(Integer, ForeignKey("employees.id"))

    logistics_address = Column(String(255), nullable=True)
    logistics_departure = Column(DateTime, nullable=True)
    logistics_arrival = Column(DateTime, nullable=True)
    logistics_status = Column(
        SAEnum(LogisticsStatus, values_callable=lambda e: [v.value for v in e]),
        default=LogisticsStatus.PENDING,
    )
    logistics_route = Column(Text, nullable=True)

    deal_type = relationship("DealType", back_populates="deals")
    client = relationship("Client", back_populates="deals")
    creator = relationship("Employee", foreign_keys=[created_by], back_populates="deals_created")
    updater = relationship("Employee", foreign_keys=[updated_by], back_populates="deals_updated")
    deal_products = relationship("DealProduct", back_populates="deal", cascade="all, delete-orphan")
    deal_employee_roles = relationship("DealEmployeeRole", back_populates="deal", cascade="all, delete-orphan")
    history = relationship("DealHistory", back_populates="deal", cascade="all, delete-orphan")


class DealProduct(Base):
    __tablename__ = "deal_products"
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("deals.id", ondelete="CASCADE"), nullable=True)
    name = Column(String, nullable=False)
    tech_card = Column(JSON, nullable=True)   # список этапов (например, ["раскрой", "сварка", "окраска"])

    deal = relationship("Deal", back_populates="deal_products")
    stages = relationship("DealProductStage", back_populates="deal_product", cascade="all, delete-orphan")


class DealProductStage(Base):
    __tablename__ = "deal_product_stages"
    id = Column(Integer, primary_key=True)
    deal_product_id = Column(Integer, ForeignKey("deal_products.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    sequence = Column(Integer, nullable=False)

    assigned_role_id = Column(Integer, ForeignKey("roles.id"), nullable=True)
    assigned_employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)

    status = Column(
        SAEnum(StageStatus, values_callable=lambda e: [v.value for v in e]),
        default=StageStatus.PENDING,
    )
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    completed_quantity = Column(Integer, default=0)
    defect_quantity = Column(Integer, default=0)

    __table_args__ = (UniqueConstraint('deal_product_id', 'sequence', name='uix_stage_sequence'),)

    deal_product = relationship("DealProduct", back_populates="stages")
    task = relationship("Task", back_populates="deal_product_stages")
    assigned_employee = relationship("Employee", foreign_keys=[assigned_employee_id], back_populates="assigned_tasks")
    assigned_role = relationship("Role", foreign_keys=[assigned_role_id], back_populates="assigned_tasks")
    notifications = relationship("Notification", back_populates="deal_stage", cascade="all, delete-orphan")


class EmployeeRole(Base):
    __tablename__ = "employee_roles"
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)

    employee = relationship("Employee", back_populates="employee_roles")
    role = relationship("Role", back_populates="employee_roles")


class DealEmployeeRole(Base):
    __tablename__ = "deal_employee_roles"
    deal_id = Column(Integer, ForeignKey("deals.id", ondelete="CASCADE"), primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)

    deal = relationship("Deal", back_populates="deal_employee_roles")
    employee = relationship("Employee", back_populates="deal_employee_roles")
    role = relationship("Role", back_populates="deal_employee_roles")


class DealHistory(Base):
    __tablename__ = "deal_history"
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("deals.id", ondelete="CASCADE"), nullable=False)
    changed_at = Column(DateTime, default=datetime.now)
    changed_by = Column(Integer, ForeignKey("employees.id"))
    field_name = Column(String(50))
    old_value = Column(Text)
    new_value = Column(Text)

    deal = relationship("Deal", back_populates="history")
    changer = relationship("Employee")


class IP(Base):
    __tablename__ = "ip_list"
    id = Column(Integer, primary_key=True)
    name = Column(String(20), unique=True, nullable=False)


class MP(Base):
    __tablename__ = "mp_list"
    id = Column(Integer, primary_key=True)
    name = Column(String(20), unique=True, nullable=False)