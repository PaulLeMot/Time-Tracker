from fastapi import Request
from fastapi.responses import StreamingResponse
import asyncio

admin_queues = set()

async def notify_admin_clients():
    for q in list(admin_queues):
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