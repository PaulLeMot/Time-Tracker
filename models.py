import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey, Text, UniqueConstraint, Date, Boolean
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

    employee_roles = relationship("EmployeeRole", back_populates="employee", cascade="all, delete-orphan")
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

    employee = relationship("Employee", foreign_keys=[employee_id], back_populates="notifications")
    admin = relationship("Employee", foreign_keys=[admin_id], back_populates="admin_notifications")


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
    name = Column(String(50), nullable=False)
    deals = relationship("Deal", back_populates="deal_type")

class Deal(Base):
    __tablename__ = "deals"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    deal_type_id = Column(Integer, ForeignKey("deal_types.id"))
    ip_id = Column(Integer, ForeignKey("ip_list.id"), nullable=True)
    mp_id = Column(Integer, ForeignKey("mp_list.id"), nullable=True)

    deal_type = relationship("DealType", back_populates="deals")
    ip = relationship("IP", back_populates="deals")
    mp = relationship("MP", back_populates="deals")
    deal_products = relationship("DealProductType", back_populates="deal", cascade="all, delete-orphan")

class DealProductType(Base):
    __tablename__ = "deal_products"
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("deals.id"), nullable = True)
    product_id = Column(Integer, ForeignKey("product_types.id"), nullable = True)
    quantity = Column(Integer, nullable = True)

    deal = relationship("Deal", back_populates="deal_products")
    product_type = relationship("ProductType", back_populates="deal_products")

class ProductType(Base):
    __tablename__ = "product_types"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    tech_card_id = Column(Integer, ForeignKey("tech_cards.id"), nullable=True)
    tech_card = relationship("TechCard", back_populates="products")
    deal_products = relationship("DealProductType", back_populates="product_type")

class TechCard(Base):
    __tablename__ = "tech_cards"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    products = relationship("ProductType", back_populates="tech_card")
    tech_card_tasks = relationship("TechCardTask", back_populates="tech_card")

class TaskType(Base):
    __tablename__ = "task_types"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    tasks = relationship("Task", back_populates="task_type")

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    task_type_id = Column(Integer, ForeignKey("task_types.id"), nullable=True)

    task_type = relationship("TaskType", back_populates="tasks")
    tech_card_tasks = relationship("TechCardTask", back_populates="task")
    role_tasks = relationship("RoleTask", back_populates="task", cascade="all, delete-orphan")

class TechCardTask(Base):
    __tablename__="tech_card_tasks"
    id = Column(Integer, primary_key=True)
    tech_card_id=Column(Integer, ForeignKey("tech_cards.id"), nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    sequence = Column(Integer, nullable = False)
    task = relationship("Task", back_populates="tech_card_tasks")
    tech_card = relationship("TechCard", back_populates="tech_card_tasks")

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    allow_multiple = Column(Boolean, default=True)
    employee_roles = relationship("EmployeeRole", back_populates="role", cascade="all, delete-orphan")
    role_tasks = relationship("RoleTask", back_populates="role", cascade="all, delete-orphan")

class RoleTask(Base):
    __tablename__ = "role_tasks"

    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)

    role = relationship("Role", back_populates="role_tasks")
    task = relationship("Task", back_populates="role_tasks")

class EmployeeRole(Base):
    __tablename__ = "employee_roles"
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True)
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    employee = relationship("Employee", back_populates="employee_roles")
    role = relationship("Role", back_populates="employee_roles")

class IP(Base):
    __tablename__ = "ip_list"
    id = Column(Integer, primary_key=True)
    name = Column(String(20), unique=True, nullable=False)
    deals = relationship("Deal", back_populates="ip")

class MP(Base):
    __tablename__ = "mp_list"
    id = Column(Integer, primary_key=True)
    name = Column(String(20), unique=True, nullable=False)
    deals = relationship("Deal", back_populates="mp")