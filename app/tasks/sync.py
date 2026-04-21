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


@celery_app.task(name="app.tasks.sync.backfill_user_snapshots")
def backfill_user_snapshots(user_id: str) -> dict:
    """
    Backfill portfolio snapshots for a single user from their earliest trade
    date up to today. Auto-triggered after the first trade is created.
    """
    import asyncio
    from datetime import date
    from sqlalchemy import select, func
    from app.database import AsyncSessionLocal
    from app.db.crud_analytics import backfill_portfolio_snapshots, backfill_daily_pnl
    from app.models.trade import Trade
    import uuid

    user_uuid = uuid.UUID(user_id)

    async def run():
        async with AsyncSessionLocal() as db:
            # Find earliest trade date for this user
            stmt = select(func.min(Trade.trade_date)).where(Trade.user_id == user_uuid)
            earliest = (await db.execute(stmt)).scalar()
            if earliest is None:
                return {"status": "no_trades"}
            start_date = earliest if isinstance(earliest, date) else earliest.date()
            end_date = date.today()

            pnl_rows = await backfill_daily_pnl(db, user_uuid)
            snap_rows = await backfill_portfolio_snapshots(db, user_uuid, start_date, end_date)
            return {"pnl_rows": pnl_rows, "snapshot_rows": snap_rows}

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        result = asyncio.ensure_future(run())
    else:
        result = asyncio.run(run())

    return {"status": "success", "user_id": user_id, "result": result}


@celery_app.task(name="app.tasks.sync.compute_end_of_day_analytics")
def compute_end_of_day_analytics() -> dict:
    """
    Computes daily PnL and snapshots for all active users.
    Also fills any missing historical snapshot dates so new users
    who joined mid-cycle are always caught up.
    Triggered by Celery Beat at EOD.
    """
    import asyncio
    import pytz
    from datetime import datetime, date
    from sqlalchemy import select, func
    from app.database import AsyncSessionLocal
    from app.db.crud_analytics import backfill_portfolio_snapshots, backfill_daily_pnl
    from app.engine.pnl_engine import compute_daily_total_pnl
    from app.models.user import User
    from app.models.trade import Trade
    from app.models.daily_portfolio_snapshot import DailyPortfolioSnapshot

    async def run():
        async with AsyncSessionLocal() as db:
            users = (await db.execute(select(User))).scalars().all()
            total_snaps = 0

            for u in users:
                try:
                    tz = pytz.timezone(u.timezone)
                except Exception:
                    tz = pytz.UTC
                local_today = datetime.now(tz).date()

                # Daily PnL update
                await compute_daily_total_pnl(db, u.id, local_today)

                # Find earliest trade date
                earliest_stmt = select(func.min(Trade.trade_date)).where(Trade.user_id == u.id)
                earliest = (await db.execute(earliest_stmt)).scalar()
                if earliest is None:
                    continue
                start_date = earliest if isinstance(earliest, date) else earliest.date()

                # Backfill the full range from first trade to today
                # (upsert is idempotent, existing rows are overwritten with fresh values)
                count = await backfill_portfolio_snapshots(db, u.id, start_date, local_today)
                total_snaps += count

            return total_snaps

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        snapshot_count = asyncio.ensure_future(run())
    else:
        snapshot_count = asyncio.run(run())

    return {"status": "success", "snapshots_created": snapshot_count}
