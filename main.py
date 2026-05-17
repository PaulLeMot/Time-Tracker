from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from database import engine, Base, AsyncSessionLocal
from routers import timelog, admin, auth, employee_notifications
from starlette.middleware.sessions import SessionMiddleware
import os
from backup import schedule_backup
from crud import auto_close_shifts, get_employees, create_employee, set_employee_password
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from models import SystemSetting
from sse import employee_events_endpoint

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        admins = await get_employees(db, active_only=False)
        admin_exists = any(e.is_admin == 1 for e in admins)
        
        if not admin_exists:
            admin_username = os.getenv("ADMIN_USERNAME", "admin")
            admin_fullname = os.getenv("ADMIN_FULLNAME", "System Administrator")
            admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
            new_admin = await create_employee(db, username=admin_username, full_name=admin_fullname)
            new_admin.is_admin = 1
            new_admin.is_monitor = 1
            await set_employee_password(db, new_admin.id, admin_password)
            await db.commit()
            print(f"Created admin user: {admin_username} / {admin_password}")

        stmt = select(SystemSetting).where(SystemSetting.key == "rounding_interval_minutes")
        result = await db.execute(stmt)
        if not result.scalar_one_or_none():
            db.add(SystemSetting(key="rounding_interval_minutes", value="15"))
            await db.commit()
            print("✅ Created default rounding setting: 15 minutes")

    schedule_backup()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(scheduled_auto_close, CronTrigger(hour=5, minute=0))
    scheduler.start()
    yield

app = FastAPI(title="TimeTracker API", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "your-secret-key-change-it"))
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(timelog.router)
app.include_router(admin.router)
app.include_router(admin.page_router)
app.include_router(admin.public_router)
app.include_router(admin.notifications_router)
app.include_router(auth.router)
app.include_router(employee_notifications.router)
from sse import admin_events_endpoint, monitor_events_endpoint
app.add_api_route("/api/admin/events", endpoint=admin_events_endpoint, methods=["GET"])
app.add_api_route("/api/monitor/events", endpoint=monitor_events_endpoint, methods=["GET"])
app.add_api_route("/api/employee/events", endpoint=employee_events_endpoint, methods=["GET"])

@app.get("/")
async def root():
    return {"message": "TimeTracker API is running"}

async def scheduled_auto_close():
    async with AsyncSessionLocal() as db:
        await auto_close_shifts(db)