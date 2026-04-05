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


@celery_app.task(name="app.tasks.sync.take_daily_snapshot")
def take_daily_snapshot() -> dict:
    """
    Take a daily portfolio snapshot for all active users.
    Triggered by Celery Beat at 3:35 PM IST each trading day.
    """
    import asyncio
    from app.database import SessionLocal
    from app.db.crud_analytics import compute_and_save_snapshots
    
    async def run():
        async with SessionLocal() as db:
            count = await compute_and_save_snapshots(db)
            return count

    loop = asyncio.get_event_loop()
    snapshot_count = loop.run_until_complete(run())
    
    return {"status": "success", "snapshots_created": snapshot_count}
