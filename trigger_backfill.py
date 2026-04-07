import asyncio
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.api.endpoints.analytics import backfill_portfolio_snapshots
from datetime import date, timedelta
from app.models.user import User

async def run_backfill():
    db = SessionLocal()
    # get first user
    user = db.query(User).first()
    if not user:
        print("No users found.")
        return
        
    print(f"Running backfill for user: {user.email}")
    today = date.today()
    start = today - timedelta(days=365)
    
    await backfill_portfolio_snapshots(start, today, user, db)
    print("Backfill complete!")

if __name__ == "__main__":
    asyncio.run(run_backfill())
