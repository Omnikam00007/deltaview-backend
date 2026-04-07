import uuid
from datetime import date
from typing import List, Tuple

from sqlalchemy import select, asc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.holding_lot import HoldingLot
from app.models.holding import Holding
from app.models.trade import Trade
from app.models.realized_pnl import RealizedPnl
from app.models.daily_pnl import DailyPnl
from app.models.instrument import Instrument

async def process_fifo_sell(
    db: AsyncSession,
    user_id: uuid.UUID,
    broker_account_id: uuid.UUID,
    instrument_id: uuid.UUID,
    sell_qty: float,
    sell_price: float,
    sell_trade_id: uuid.UUID,
    sell_date: date,
) -> Tuple[float, float, float]:
    """
    Consumes oldest HoldingLots for a user/instrument using FIFO logic.
    Returns: (total_realized_pnl, total_cost_basis_consumed, remaining_sell_qty)
    """
    # 1. Fetch available lots locked for update
    stmt = (
        select(HoldingLot)
        .where(
            HoldingLot.user_id == user_id,
            HoldingLot.instrument_id == instrument_id,
            HoldingLot.quantity > 0
        )
        .order_by(asc(HoldingLot.created_at))
        .with_for_update()
    )
    result = await db.execute(stmt)
    lots = result.scalars().all()

    remaining_qty = sell_qty
    total_realized = 0.0
    total_cost_consumed = 0.0

    for lot in lots:
        if remaining_qty <= 0:
            break
        
        consume_qty = min(float(lot.quantity), remaining_qty)
        cost_basis = float(lot.avg_cost)
        
        # Calculate PnL for this consumed portion
        realized_pnl = consume_qty * (sell_price - cost_basis)
        
        total_realized += realized_pnl
        total_cost_consumed += (consume_qty * cost_basis)
        
        # Update or delete lot
        lot.quantity = float(lot.quantity) - consume_qty
        remaining_qty -= consume_qty

        # Write RealizedPnl constituent row for this lot match
        pnl_entry = RealizedPnl(
            user_id=user_id,
            broker_account_id=broker_account_id,
            instrument_id=instrument_id,
            buy_trade_id=lot.trade_id,
            sell_trade_id=sell_trade_id,
            quantity=consume_qty,
            buy_value=consume_qty * cost_basis,
            sell_value=consume_qty * sell_price,
            gross_pnl=realized_pnl,
            net_pnl=realized_pnl,  # omitting charges granularity per lot for now
            buy_date=lot.created_at.date(),
            sell_date=sell_date,
            holding_period_days=(sell_date - lot.created_at.date()).days,
            tax_category="STCG" if (sell_date - lot.created_at.date()).days < 365 else "LTCG",
            financial_year=f"{sell_date.year}-{str(sell_date.year+1)[-2:]}" if sell_date.month >= 4 else f"{sell_date.year-1}-{str(sell_date.year)[-2:]}"
        )
        db.add(pnl_entry)

    # Any remaining_qty > 0 implies short-selling or data inconsistency.
    return (total_realized, total_cost_consumed, remaining_qty)

async def compute_daily_total_pnl(db: AsyncSession, user_id: uuid.UUID, target_date: date):
    """
    Computes and upserts DailyPnl for a user on a given date.
    unrealized_pnl = (current_holdings_value - current_cost_basis) - (previous_holdings_value - previous_cost_basis)
    realized_pnl = Sum of RealizedPnl for that date
    total_pnl = realized + unrealized
    """
    # 1. Fetch Realized PnL for the date
    stmt_realized = (
        select(func.coalesce(func.sum(RealizedPnl.net_pnl), 0))
        .where(
            RealizedPnl.user_id == user_id,
            RealizedPnl.sell_date == target_date
        )
    )
    realized_pnl = float((await db.execute(stmt_realized)).scalar() or 0.0)

    # 2. Get current holdings value to calculate total unrealized PnL as of today
    # Note: A true time-traveling calculation requires snapshotting yesterday's exact state.
    # We will compute the absolute current snapshot of unrealized_pnl.
    stmt_holdings = (
        select(
            func.sum(Holding.current_value).label("market_value"),
            func.sum(Holding.quantity * Holding.avg_cost).label("cost_basis")
        )
        .where(Holding.user_id == user_id)
    )
    h_res = (await db.execute(stmt_holdings)).one_or_none()
    
    current_market_value = float(h_res.market_value if h_res and h_res.market_value else 0.0)
    current_cost_basis = float(h_res.cost_basis if h_res and h_res.cost_basis else 0.0)
    total_unrealized = current_market_value - current_cost_basis

    # To calculate the daily DELTA in unrealized PnL, we subtract yesterday's total unrealized P&L
    # from the DailyPortfolioSnapshot or previous DailyPnl.
    # Since we are refactoring, we'll assume we can pull yesterday's from DailyPortfolioSnapshot.
    from app.models.daily_portfolio_snapshot import DailyPortfolioSnapshot
    from datetime import timedelta
    
    stmt_yesterday = (
        select(DailyPortfolioSnapshot.total_unrealized_pnl)
        .where(
            DailyPortfolioSnapshot.user_id == user_id,
            DailyPortfolioSnapshot.snapshot_date < target_date
        )
        .order_by(DailyPortfolioSnapshot.snapshot_date.desc())
        .limit(1)
    )
    y_res = (await db.execute(stmt_yesterday)).scalar()
    yesterday_unrealized = float(y_res or 0.0)
    
    daily_unrealized_pnl = total_unrealized - yesterday_unrealized
    total_daily_pnl = realized_pnl + daily_unrealized_pnl

    # 3. Trade count
    stmt_trades = select(func.count(Trade.id)).where(Trade.user_id == user_id, Trade.trade_date == target_date)
    trade_count = (await db.execute(stmt_trades)).scalar() or 0

    # 4. Upsert into DailyPnl
    values = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "trade_date": target_date,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": daily_unrealized_pnl,
        "total_pnl": total_daily_pnl,
        "trade_count": trade_count,
        "segment": "equity"
    }

    stmt = pg_insert(DailyPnl).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "trade_date", "segment"],
        set_={
            "realized_pnl": stmt.excluded.realized_pnl,
            "unrealized_pnl": stmt.excluded.unrealized_pnl,
            "total_pnl": stmt.excluded.total_pnl,
            "trade_count": stmt.excluded.trade_count,
        }
    )
    await db.execute(stmt)
