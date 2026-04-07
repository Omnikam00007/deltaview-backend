"""Background sync tasks (broker data, P&L recalculation, snapshots)."""
from app.tasks import celery_app


@celery_app.task(name="app.tasks.sync.broker_sync")
def broker_sync(broker_account_id: str) -> dict:
    """
    Sync trades and holdings from a broker account.
    TODO: implement per-broker SDK calls (Kite, Upstox, Groww).
    """
    return {"status": "pending", "broker_account_id": broker_account_id}


@celery_app.task(name="app.tasks.sync.recalculate_pnl")
def recalculate_pnl(user_id: str) -> dict:
    """
    Re-run FIFO P&L calculation for a user after new trades arrive.
    TODO: implement FIFO matching logic.
    """
    return {"status": "pending", "user_id": user_id}


@celery_app.task(name="app.tasks.sync.update_unrealized_pnl")
def update_unrealized_pnl() -> dict:
    """
    Fetch daily prices for all user holdings and update ltp, current_value, and pnl.
    Triggered daily by Celery Beat.
    """
    import asyncio
    from app.database import SessionLocal
    from app.db.crud_holding import refresh_unrealized_pnl
    
    async def run():
        async with SessionLocal() as db:
            count = await refresh_unrealized_pnl(db, user_id=None)
            return count

    loop = asyncio.get_event_loop()
    updated_count = loop.run_until_complete(run())
    
    return {"status": "success", "updated_holdings_count": updated_count}


@celery_app.task(name="app.tasks.sync.compute_end_of_day_analytics")
def compute_end_of_day_analytics() -> dict:
    """
    Computes daily PnL and snapshots for all active users.
    Triggered by Celery Beat at EOD.
    """
    import asyncio
    import pytz
    from datetime import datetime
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.db.crud_analytics import compute_and_save_snapshots
    from app.engine.pnl_engine import compute_daily_total_pnl
    from app.models.user import User
    
    async def run():
        async with AsyncSessionLocal() as db:
            users = (await db.execute(select(User))).scalars().all()
            for u in users:
                try:
                    tz = pytz.timezone(u.timezone)
                except Exception:
                    tz = pytz.UTC
                local_today = datetime.now(tz).date()
                
                # Daily PnL for Unrealized + Realized updates
                await compute_daily_total_pnl(db, u.id, local_today)
            
            # Daily Portfolio Snapshot
            count = await compute_and_save_snapshots(db)
            return count

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
        
    if loop and loop.is_running():
        # Fallback if running inside an existing loop (fastapi tests, etc)
        snapshot_count = asyncio.ensure_future(run())
    else:
        snapshot_count = asyncio.run(run())
    
    return {"status": "success", "snapshots_created": snapshot_count}
