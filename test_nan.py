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
        response = await ac.get("/api/v1/analytics/snapshots", headers={"Authorization": f"Bearer {token}"})
        print("Status:", response.status_code)
        text = response.text
        print("Contains NaN:", "NaN" in text)
        print("Contains Infinity:", "Infinity" in text)

asyncio.run(main())
