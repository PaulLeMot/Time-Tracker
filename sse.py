import asyncio
from fastapi import Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
import crud

admin_queues = set()
monitor_queues = set()
employee_queues = {}
async def notify_admin_clients():
    for q in list(admin_queues):
        await q.put("refresh")

async def notify_monitor_clients():
    for q in list(monitor_queues):
        await q.put("refresh")

async def admin_events_endpoint(request: Request):
    queue = asyncio.Queue()
    admin_queues.add(queue)
    async def event_stream():
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: update\ndata: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            admin_queues.discard(queue)
    return StreamingResponse(event_stream(), media_type="text/event-stream")

async def monitor_events_endpoint(request: Request, db: AsyncSession = Depends(get_db)):
    employee_id = request.session.get("employee_id")
    is_allowed = False
    
    if employee_id:
        employee = await crud.get_employee_by_id(db, employee_id)
        if employee and (employee.is_admin == 1 or employee.is_monitor == 1):
            is_allowed = True
    
    if not is_allowed and not request.session.get("is_monitor"):
        raise HTTPException(403, "Access denied")
    queue = asyncio.Queue()
    monitor_queues.add(queue)
    async def event_stream():
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: update\ndata: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            monitor_queues.discard(queue)
    return StreamingResponse(event_stream(), media_type="text/event-stream")

async def notify_employee(employee_id: int):
    if employee_id in employee_queues:
        for q in list(employee_queues[employee_id]):
            await q.put("notification")

async def employee_events_endpoint(request: Request, db: AsyncSession = Depends(get_db)):
    employee_id = request.session.get("employee_id")
    if not employee_id:
        raise HTTPException(401, "Unauthorized")
    employee = await crud.get_employee_by_id(db, employee_id)
    if not employee:
        raise HTTPException(401, "Employee not found")
    queue = asyncio.Queue()
    if employee.id not in employee_queues:
        employee_queues[employee.id] = set()
    employee_queues[employee.id].add(queue)
    async def event_stream():
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: update\ndata: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            employee_queues[employee.id].discard(queue)
            if not employee_queues[employee.id]:
                del employee_queues[employee.id]
    return StreamingResponse(event_stream(), media_type="text/event-stream")