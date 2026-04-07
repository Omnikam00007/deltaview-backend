import asyncio
from app.database import AsyncSessionLocal
from app.db.crud_analytics import backfill_daily_pnl
from sqlalchemy import select
from app.models.user import User

async def run():
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User))).scalars().all()
        if not users:
            print("No users found")
            return
        user_id = users[0].id
        print(f"Testing backfill for user {user_id}")
        count = await backfill_daily_pnl(db, user_id)
        print(f"Rows upserted: {count}")

if __name__ == "__main__":
    asyncio.run(run())
