from fastapi import FastAPI
from contextlib import asynccontextmanager
from database import engine, Base
from routers import timelog

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="TimeTracker API", lifespan=lifespan)
app.include_router(timelog.router)
@app.get("/")
async def root():
    return {"message": "TimeTracker API is running"}