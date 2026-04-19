import asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.daily_portfolio_snapshot import DailyPortfolioSnapshot

async def main():
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User))).scalars().all()
        for u in users:
            stmt = select(DailyPortfolioSnapshot).where(DailyPortfolioSnapshot.user_id == u.id)
            snaps = (await db.execute(stmt)).scalars().all()
            print(f"User: {u.email}, ID: {u.id}, Snaps: {len(snaps)}")
            
asyncio.run(main())
