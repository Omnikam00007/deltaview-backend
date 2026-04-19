import asyncio
from httpx import AsyncClient
from app.database import AsyncSessionLocal
from app.models.user import User
from sqlalchemy import select
from app.core.security import create_access_token

async def main():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).where(User.email == 'omnikam33@gmail.com'))
        user = res.scalar_one_or_none()
        token = create_access_token(str(user.id))
        
    async with AsyncClient(base_url="http://127.0.0.1:8000") as ac:
        response = await ac.get("/api/v1/analytics/snapshots?start_date=2026-04-10&end_date=2026-04-17", headers={"Authorization": f"Bearer {token}"})
        data = response.json()
        print("Status:", response.status_code)
        print("Response length for 2026-04-10 to 2026-04-17:", len(data))
        if len(data) > 0:
            print("First item date:", data[0]['snapshot_date'])
        
        response2 = await ac.get("/api/v1/analytics/snapshots?start_date=2025-04-10&end_date=2026-04-17", headers={"Authorization": f"Bearer {token}"})
        data2 = response2.json()
        print("Response length for 2025-04-10 to 2026-04-17:", len(data2))

asyncio.run(main())
