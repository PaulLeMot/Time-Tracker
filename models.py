from sqlalchemy import Column, Integer, String, DateTime, Time, JSON, Enum, ForeignKey, Text
from database import Base
from datetime import datetime
import enum
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

class NotificationType(enum.Enum):
    REPRIMAND = "reprimand"
    WARNING = "warning"
    COMMENDATION = "commendation"

class NotificationStatus(enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    REJECTED = "rejected"

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    admin_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    type = Column(Enum(NotificationType), nullable=False)
    message = Column(Text, nullable=False)
    status = Column(Enum(NotificationStatus), default=NotificationStatus.DRAFT)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    source = Column(String(20), default="admin")
    extra_data = Column(JSON, nullable=True)

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
    code = Column(String, unique=True, nullable=False)
    product_type = Column(String, nullable=False)
    fandom = Column(String, nullable=True)
    name = Column(String, nullable=False)