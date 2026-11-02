"""Explicit READ ONLY export adapter; never imports main, schedules jobs or runs DDL."""
import asyncio
import json


async def export():
    from sqlalchemy import text
    from database import AsyncSessionLocal, engine
    engine.echo = False
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text('SET TRANSACTION READ ONLY'))
            result = await session.execute(text('SELECT code, product_type, name, fandom FROM products ORDER BY code'))
            rows = [dict(row) for row in result.mappings()]
            await session.rollback()
            return rows
    finally:
        await engine.dispose()


if __name__ == '__main__':
    print(json.dumps(asyncio.run(export()), ensure_ascii=True))
