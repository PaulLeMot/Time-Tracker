from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from database import engine, Base
from routers import timelog, admin, auth
from starlette.middleware.sessions import SessionMiddleware
import os
from backup import schedule_backup
from crud import auto_close_shifts
from database import AsyncSessionLocal
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    schedule_backup()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(scheduled_auto_close, CronTrigger(hour=22, minute=0))
    scheduler.start()
    yield

app = FastAPI(title="TimeTracker API", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "your-secret-key-change-it"))
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(timelog.router)
app.include_router(admin.router)
app.include_router(admin.page_router)
app.include_router(admin.public_router)
app.include_router(auth.router)
from sse import admin_events_endpoint
app.add_api_route("/api/admin/events", endpoint=admin_events_endpoint, methods=["GET"])


@app.get("/")
async def root():
    return {"message": "TimeTracker API is running"}

async def scheduled_auto_close():
    async with AsyncSessionLocal() as db:
        await auto_close_shifts(db)