from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from database import engine, Base
from routers import timelog, admin

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="TimeTracker API", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(timelog.router)
app.include_router(admin.router)
app.include_router(admin.page_router)
app.include_router(admin.public_router)
@app.get("/")
async def root():
    return {"message": "TimeTracker API is running"}