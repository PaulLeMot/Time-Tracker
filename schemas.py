from pydantic import BaseModel

class TimeLogCreate(BaseModel):
    user_id: int
    action: str

# ---------- ДОПОЛНЕНИЕ ДЛЯ ПЕСОЧНИЦЫ ----------
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel

class DealTypeResponse(BaseModel):
    id: int
    code: str
    name: str

class ClientResponse(BaseModel):
    id: int
    code: str
    name: str

class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]

class StageResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]

class DealProductCreate(BaseModel):
    product_id: int
    quantity: int

class DealCreate(BaseModel):
    title: str
    deal_type_id: int
    client_id: int
    planned_date: date
    products: List[DealProductCreate]
    product_stages: dict   # {product_id: [stage_id, ...]}

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    default_stages: Optional[List[int]] = None