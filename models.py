from sqlalchemy import Column, Integer, String, DateTime
from database import Base

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    qr_code_secret = Column(String, unique=True, nullable=False)
    is_active = Column(Integer, default=1)
    password = Column(String, nullable=True)
    
class TimeEntry(Base):
    __tablename__ = "time_entries"
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, index=True)
    action = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    source = Column(String, default="qr")