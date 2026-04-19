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
        print("Status 1:", response.status_code)
        if response.status_code != 200:
            print("Response 1:", response.text)
            
        response2 = await ac.get("/api/v1/analytics/snapshots?start_date=&end_date=", headers={"Authorization": f"Bearer {token}"})
        print("Status 2:", response2.status_code)
        if response2.status_code != 200:
            print("Response 2:", response2.text)

asyncio.run(main())
