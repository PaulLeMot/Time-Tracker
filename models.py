import enum
from datetime import datetime
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from enum import Enum
from database import Base

# ========================== ENUMS ==========================

class NotificationType(str, enum.Enum):
    REPRIMAND = "reprimand"
    WARNING = "warning"
    COMMENDATION = "commendation"
    PERFORMANCE_REVIEW = "performance_review"
    TASK_ASSIGNMENT = "task_assignment"

class NotificationStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    REJECTED = "rejected"

class DayType(str, Enum):
    WORK = "WORK"
    OFF = "OFF"
    VACATION = "VACATION"
    SICK = "SICK"

class TaskExecutionStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    ON_BREAK = "on_break"
    COMPLETED = "completed"

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
    schedule_data = Column(JSONB, nullable=True)

    employee_roles = relationship("EmployeeRole", back_populates="employee", cascade="all, delete-orphan")
    notifications = relationship("Notification", foreign_keys="Notification.employee_id", back_populates="employee")
    admin_notifications = relationship("Notification", foreign_keys="Notification.admin_id", back_populates="admin")
    task_executions = relationship("TaskExecution", back_populates="employee")
    task_production_distributions = relationship("TaskProductionDistribution", back_populates="employee")


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
    task_execution = relationship("TaskExecution", back_populates="notification", uselist=False)


class Explanation(Base):
    __tablename__ = "explanations"
    id = Column(Integer, primary_key=True)
    notification_id = Column(Integer, ForeignKey("notifications.id"), unique=True, nullable=False)
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
    deal_type_tasks = relationship("DealTypeTask", back_populates="deal_type", cascade="all, delete-orphan")

class Deal(Base):
    __tablename__ = "deals"
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    deal_type_id = Column(Integer, ForeignKey("deal_types.id"))
    ip_id = Column(Integer, ForeignKey("ip_list.id", ondelete="SET NULL"), nullable=True)
    mp_id = Column(Integer, ForeignKey("mp_list.id", ondelete="SET NULL"), nullable=True)
    status = Column(String, default="in_progress")

    deal_type = relationship("DealType", back_populates="deals")
    ip = relationship("IP", back_populates="deals")
    mp = relationship("MP", back_populates="deals")
    deal_products = relationship("DealProductType", back_populates="deal", cascade="all, delete-orphan")
    task_completion_data = relationship("TaskCompletionData", back_populates="deal", cascade="all, delete-orphan")

class DealProductType(Base):
    __tablename__ = "deal_products"
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("deals.id", ondelete="CASCADE"), nullable = True)
    product_id = Column(Integer, ForeignKey("product_types.id"), nullable = True)
    quantity = Column(Integer, nullable = True)

    deal = relationship("Deal", back_populates="deal_products")
    product_type = relationship("ProductType", back_populates="deal_products")

class DealTypeTask(Base):
    __tablename__ = "deal_type_tasks"
    deal_type_id = Column(Integer, ForeignKey("deal_types.id", ondelete="CASCADE"), primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    is_enabled = Column(Boolean, default=True)
    deal_type = relationship("DealType", back_populates="deal_type_tasks")
    task = relationship("Task", back_populates="deal_type_tasks")
    __table_args__ = (
        Index("idx_deal_type_tasks_deal_type_id", "deal_type_id"),
        Index("idx_deal_type_tasks_task_id", "task_id"),
    )

class ProductType(Base):
    __tablename__ = "product_types"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    full_name = Column(Text, nullable=True)
    tech_card_id = Column(Integer, ForeignKey("tech_cards.id"), nullable=True)
    tech_card = relationship("TechCard", back_populates="products")
    deal_products = relationship("DealProductType", back_populates="product_type")
    task_completion_data = relationship("TaskCompletionData", back_populates="product_type")

class TechCard(Base):
    __tablename__ = "tech_cards"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    products = relationship("ProductType", back_populates="tech_card")
    tech_card_tasks = relationship("TechCardTask", back_populates="tech_card")

class TaskType(Base):
    __tablename__ = "task_types"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    tasks = relationship("Task", back_populates="task_type")

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    task_type_id = Column(Integer, ForeignKey("task_types.id"), nullable=True)

    task_type = relationship("TaskType", back_populates="tasks")
    tech_card_tasks = relationship("TechCardTask", back_populates="task")
    role_tasks = relationship("RoleTask", back_populates="task", cascade="all, delete-orphan")
    deal_type_tasks = relationship("DealTypeTask", back_populates="task", cascade="all, delete-orphan")
    task_completion_data = relationship("TaskCompletionData", back_populates="task", cascade="all, delete-orphan")
    independent_tasks = relationship("IndependentTask", back_populates="task")
    product_points = relationship("TaskProductPoint", back_populates="task", cascade="all, delete-orphan")
    __table_args__ = (Index("idx_tasks_type_id", "task_type_id"),)


class IndependentTask(Base):
    """Отдельный экземпляр задачи, который не относится к сделке."""
    __tablename__ = "independent_tasks"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False, index=True)
    title = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    due_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    created_by_id = Column(Integer, ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    completion_data = Column(JSONB, nullable=True)

    task = relationship("Task", back_populates="independent_tasks")
    created_by = relationship("Employee", foreign_keys=[created_by_id])
    assignees = relationship(
        "IndependentTaskAssignee",
        back_populates="independent_task",
        cascade="all, delete-orphan",
    )


class IndependentTaskAssignee(Base):
    __tablename__ = "independent_task_assignees"

    independent_task_id = Column(
        Integer,
        ForeignKey("independent_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="RESTRICT"), primary_key=True)
    notification_id = Column(
        Integer,
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    is_main = Column(Boolean, nullable=False, default=False)
    assigned_at = Column(DateTime, nullable=False, default=datetime.now)

    independent_task = relationship("IndependentTask", back_populates="assignees")
    employee = relationship("Employee")
    notification = relationship("Notification")
    __table_args__ = (
        Index("ix_independent_task_assignees_employee_id", "employee_id"),
        Index(
            "uq_independent_task_main_assignee",
            "independent_task_id",
            unique=True,
            postgresql_where=text("is_main"),
        ),
    )


class TaskProductPoint(Base):
    __tablename__ = "task_product_points"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    product_type_id = Column(Integer, ForeignKey("product_types.id", ondelete="CASCADE"), nullable=False)
    points = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    task = relationship("Task", back_populates="product_points")
    product_type = relationship("ProductType")
    __table_args__ = (
        UniqueConstraint("task_id", "product_type_id", name="uq_task_product_points"),
        CheckConstraint("points >= 0", name="task_product_points_points_check"),
        Index("ix_task_product_points_task_id", "task_id"),
        Index("ix_task_product_points_product_type_id", "product_type_id"),
    )

class TechCardTask(Base):
    __tablename__="tech_card_tasks"
    id = Column(Integer, primary_key=True)
    tech_card_id=Column(Integer, ForeignKey("tech_cards.id"), nullable=False)
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

class TaskExecution(Base):
    __tablename__ = "task_executions"
    id = Column(Integer, primary_key=True)
    notification_id = Column(Integer, ForeignKey("notifications.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    status = Column(
        SAEnum(
            TaskExecutionStatus,
            name="taskexecutionstatus",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
            native_enum=False,
            length=20,
        ),
        default=TaskExecutionStatus.NOT_STARTED,
        nullable=False,
    )
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    general_comment = Column(Text, nullable=True)
    completion_percent = Column(Integer, nullable=True)

    notification = relationship("Notification", back_populates="task_execution")
    employee = relationship("Employee", back_populates="task_executions")
    breaks = relationship("TaskBreak", back_populates="task_execution", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint('notification_id', name='uq_notification_task'),
        CheckConstraint(
            "completion_percent IS NULL OR completion_percent BETWEEN 0 AND 100",
            name="ck_task_execution_completion_percent",
        ),
        Index("idx_task_executions_employee_id", "employee_id"),
        Index("idx_task_executions_notification_id", "notification_id"),
    )

class TaskBreak(Base):
    __tablename__ = "task_breaks"
    id = Column(Integer, primary_key=True)
    task_execution_id = Column(Integer, ForeignKey("task_executions.id"), nullable=False)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)  # NULL, если перерыв ещё активен

    # Связь с TaskExecution (добавить в TaskExecution)
    task_execution = relationship("TaskExecution", back_populates="breaks")

class TaskCompletionData(Base):
    __tablename__ = "task_completion_data"
    id = Column(Integer, primary_key=True)
    deal_id = Column(Integer, ForeignKey("deals.id", ondelete="CASCADE"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    product_type_id = Column(Integer, ForeignKey("product_types.id"), nullable=False)   # НОВОЕ поле
    defect_quantity = Column(Integer, default=0, nullable=False)
    defect_comment = Column(String(300), nullable=True)

    # Связи
    deal = relationship("Deal", back_populates="task_completion_data")
    task = relationship("Task", back_populates="task_completion_data")
    product_type = relationship("ProductType", back_populates="task_completion_data")  # НОВАЯ связь
    distributions = relationship("TaskProductionDistribution", back_populates="task_completion", cascade="all, delete-orphan")

    # Уникальность: одна запись на (договор, задача, тип товара)
    __table_args__ = (
        UniqueConstraint('deal_id', 'task_id', 'product_type_id', name='uq_deal_task_product'),
        Index("idx_task_completion_data_deal_id", "deal_id"),
        Index("idx_task_completion_data_task_id", "task_id"),
    )


class TaskProductionDistribution(Base):
    __tablename__ = "task_production_distribution"
    id = Column(Integer, primary_key=True)
    task_completion_id = Column(Integer, ForeignKey("task_completion_data.id", ondelete="CASCADE"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Integer, nullable=False, default=0)

    task_completion = relationship("TaskCompletionData", back_populates="distributions")
    employee = relationship("Employee", back_populates="task_production_distributions")
    __table_args__ = (
        Index("idx_task_production_distribution_employee_id", "employee_id"),
        Index("idx_task_production_distribution_task_completion_id", "task_completion_id"),
    )
