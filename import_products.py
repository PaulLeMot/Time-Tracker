import asyncio
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from models import Product
from database import DATABASE_URL

async def import_products():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    file_path = '/app/static/img/products.xlsx'
    df = pd.read_excel(file_path)

    df.columns = ['code', 'product_type', 'fandom', 'name']

    async with async_session() as session:
        for _, row in df.iterrows():
            code = str(row['code']).strip()

            stmt = select(Product).where(Product.code == code)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                print(f"Пропущен существующий код: {code}")
                continue
            product = Product(
                code=code,
                product_type=str(row['product_type']).strip(),
                fandom=str(row['fandom']).strip() if pd.notna(row['fandom']) else None,
                name=str(row['name']).strip()
            )
            session.add(product)
        await session.commit()
    print("✅ Импорт завершён")

if __name__ == "__main__":
    asyncio.run(import_products())