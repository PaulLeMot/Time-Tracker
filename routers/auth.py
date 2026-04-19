from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from database import get_db
import crud

router = APIRouter(prefix="/api/auth", tags=["auth"])

class LoginData(BaseModel):
    full_name: str
    password: str

@router.post("/login")
async def login(login_data: LoginData, request: Request, db: AsyncSession = Depends(get_db)):
    employee = await crud.get_employee_by_full_name(db, login_data.full_name)
    if not employee:
        raise HTTPException(404, "Сотрудник с таким именем не найден")
    if not employee.is_active:
        raise HTTPException(403, "Сотрудник деактивирован")
    if employee.password != login_data.password:
        raise HTTPException(401, "Неверный пароль")
    request.session["employee_id"] = employee.id
    return {"message": "Успешный вход", "employee_id": employee.id, "full_name": employee.full_name}

@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"message": "Выход выполнен"}

@router.get("/profile")
async def get_profile(request: Request, db: AsyncSession = Depends(get_db)):
    employee_id = request.session.get("employee_id")
    if not employee_id:
        raise HTTPException(401, "Не авторизован")
    employee = await crud.get_employee_by_id(db, employee_id)
    if not employee:
        request.session.clear()
        raise HTTPException(404, "Сотрудник не найден")
    return {
        "id": employee.id,
        "full_name": employee.full_name,
        "is_active": employee.is_active
    }