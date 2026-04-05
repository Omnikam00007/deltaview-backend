import uuid
from datetime import date
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.trade import Trade
from app.models.holding import Holding
from app.schemas.trade import TradeCreate


class InsufficientHoldingError(ValueError):
    """Raised when a SELL trade quantity exceeds the available holding quantity."""
    pass


async def upsert_holding_from_trade(db: AsyncSession, trade: Trade):
    """Update or create a holding based on a new trade (BUY or SELL).
    Uses row-level locking to prevent race conditions on avg_cost/quantity.
    Must be called within an active transaction.
    """
    stmt = (
        select(Holding)
        .where(
            Holding.user_id == trade.user_id,
            Holding.broker_account_id == trade.broker_account_id,
            Holding.instrument_id == trade.instrument_id,
        )
        .with_for_update()  # Lock the holding row for the duration of the transaction
    )
    result = await db.execute(stmt)
    holding = result.scalar_one_or_none()

    if trade.trade_type == "BUY":
        if holding:
            # Recalculate weighted average cost
            old_qty = float(holding.quantity)
            old_cost = float(holding.avg_cost)
            trade_qty = float(trade.quantity)
            trade_price = float(trade.price)

            new_qty = old_qty + trade_qty
            # Avoid division by zero (should never happen if new_qty > 0)
            if new_qty > 0:
                new_avg_cost = ((old_qty * old_cost) + (trade_qty * trade_price)) / new_qty
            else:
                new_avg_cost = trade_price

            holding.quantity = new_qty
            holding.avg_cost = new_avg_cost
            holding.as_of_date = trade.trade_date
        else:
            # Create new holding
            holding = Holding(
                user_id=trade.user_id,
                broker_account_id=trade.broker_account_id,
                instrument_id=trade.instrument_id,
                quantity=trade.quantity,
                avg_cost=trade.price,
                as_of_date=trade.trade_date,
            )
            db.add(holding)
            
    elif trade.trade_type == "SELL":
        if not holding or float(holding.quantity) < float(trade.quantity):
            raise InsufficientHoldingError(
                f"Cannot SELL {trade.quantity} units. "
                f"Available holding: {float(holding.quantity) if holding else 0} units."
            )
        
        # Reduce quantity, do not change average cost
        holding.quantity = float(holding.quantity) - float(trade.quantity)
        holding.as_of_date = trade.trade_date


from sqlalchemy import select, func
from app.models.realized_pnl import RealizedPnl


def _get_fy_string(d: date) -> str:
    """Return financial year string 'YYYY-YY' for a given date."""
    year = d.year if d.month >= 4 else d.year - 1
    return f"{year}-{str(year + 1)[-2:]}"


async def process_realized_pnl(db: AsyncSession, sell_trade: Trade):
    """FIFO lot matching: match SELL trade against unallocated BUY trades 
    and generate RealizedPnl records. Must be called inside transaction."""
    
    # 1. Subquery to find already allocated quantities for each BUY trade
    allocated_sq = (
        select(
            RealizedPnl.buy_trade_id,
            func.sum(RealizedPnl.quantity).label("allocated_qty")
        )
        .where(RealizedPnl.user_id == sell_trade.user_id)
        .group_by(RealizedPnl.buy_trade_id)
        .subquery()
    )

    # 2. Query ALL previous BUY trades for this instrument that still have qty available
    # Ordered by trade_date ASC, created_at ASC (FIFO)
    stmt = (
        select(Trade, func.coalesce(allocated_sq.c.allocated_qty, 0).label("allocated"))
        .outerjoin(allocated_sq, Trade.id == allocated_sq.c.buy_trade_id)
        .where(
            Trade.user_id == sell_trade.user_id,
            Trade.broker_account_id == sell_trade.broker_account_id,
            Trade.instrument_id == sell_trade.instrument_id,
            Trade.trade_type == "BUY",
            (Trade.quantity - func.coalesce(allocated_sq.c.allocated_qty, 0)) > 0
        )
        .order_by(Trade.trade_date.asc(), Trade.created_at.asc())
    )
    
    result = await db.execute(stmt)
    rows = result.all()
    
    remaining_sell_qty = float(sell_trade.quantity)
    
    for row in rows:
        buy_trade: Trade = row.Trade
        allocated = float(row.allocated)
        available_qty = float(buy_trade.quantity) - allocated
        
        match_qty = min(remaining_sell_qty, available_qty)
        
        # Financial calculations for this matched chunk
        buy_value = match_qty * float(buy_trade.price)
        sell_value = match_qty * float(sell_trade.price)
        gross_pnl = sell_value - buy_value
        
        # Simplified proportionate charges for this chunk 
        # (in a real app, you'd accurately proportion total trade charges)
        net_pnl = gross_pnl # ignoring proportional charges for now
        
        holding_days = (sell_trade.trade_date - buy_trade.trade_date).days
        
        # Tax categorization based on segment
        # Equities: 365 days. Debt/Gold: 1095 days.
        segment = (sell_trade.segment or "equity").lower()
        if segment in {"mf", "gold", "other"}:
            threshold = 1095
        else: # equity, fno, etf
            threshold = 365
            
        tax_category = "LTCG" if holding_days >= threshold else "STCG"
        
        rpnl = RealizedPnl(
            user_id=sell_trade.user_id,
            broker_account_id=sell_trade.broker_account_id,
            instrument_id=sell_trade.instrument_id,
            buy_trade_id=buy_trade.id,
            sell_trade_id=sell_trade.id,
            quantity=match_qty,
            buy_value=buy_value,
            sell_value=sell_value,
            gross_pnl=gross_pnl,
            charges={},  # To be precise, calculate proportionate charges
            net_pnl=net_pnl,
            buy_date=buy_trade.trade_date,
            sell_date=sell_trade.trade_date,
            holding_period_days=holding_days,
            tax_category=tax_category,
            financial_year=_get_fy_string(sell_trade.trade_date)
        )
        db.add(rpnl)
        
        remaining_sell_qty -= match_qty
        if remaining_sell_qty <= 0:
            break


async def create_trade(db: AsyncSession, user_id: uuid.UUID, obj_in: TradeCreate) -> Trade:
    """Create a trade and automatically manage the corresponding holding."""
    # Run operations within the current implicit transaction started by FastAPI dependencies
    db_obj = Trade(
        user_id=user_id,
        broker_account_id=obj_in.broker_account_id,
        instrument_id=obj_in.instrument_id,
        trade_type=obj_in.trade_type.upper(),
        quantity=obj_in.quantity,
        price=obj_in.price,
        trade_value=obj_in.trade_value,
        trade_date=obj_in.trade_date,
        settlement_date=obj_in.settlement_date,
        order_id=obj_in.order_id,
        segment=obj_in.segment,
        charges=obj_in.charges,
        raw_data=obj_in.raw_data,
    )
    db.add(db_obj)
    await db.flush()  # So the trade gets an ID if needed for relations

    # 2. Update the holding
    await upsert_holding_from_trade(db, db_obj)
    
    # 3. Realize P&L if it's a SELL trade (FIFO lot matching)
    if db_obj.trade_type == "SELL":
        await process_realized_pnl(db, db_obj)

    # 4. Commit all changes atomically
    await db.commit()
    
    # We must refresh the object to load relationships
    await db.refresh(db_obj, attribute_names=["instrument", "broker_account"])
    return db_obj


async def get_user_trades(
    db: AsyncSession,
    user_id: uuid.UUID,
    broker_account_id: uuid.UUID | None = None,
    instrument_id: uuid.UUID | None = None,
    trade_type: str | None = None,
    segment: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> Sequence[Trade]:
    stmt = (
        select(Trade)
        .where(Trade.user_id == user_id)
        .options(selectinload(Trade.instrument), selectinload(Trade.broker_account))
        .order_by(Trade.trade_date.desc(), Trade.created_at.desc())
    )
    if broker_account_id:
        stmt = stmt.where(Trade.broker_account_id == broker_account_id)
    if instrument_id:
        stmt = stmt.where(Trade.instrument_id == instrument_id)
    if trade_type:
        stmt = stmt.where(Trade.trade_type == trade_type.upper())
    if segment:
        stmt = stmt.where(Trade.segment == segment)
    if start_date:
        stmt = stmt.where(Trade.trade_date >= start_date)
    if end_date:
        stmt = stmt.where(Trade.trade_date <= end_date)

    result = await db.execute(stmt)
    return result.scalars().all()


async def get_trade_by_id(db: AsyncSession, trade_id: uuid.UUID, user_id: uuid.UUID) -> Trade | None:
    stmt = (
        select(Trade)
        .where(Trade.id == trade_id, Trade.user_id == user_id)
        .options(selectinload(Trade.instrument), selectinload(Trade.broker_account))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def delete_trade(db: AsyncSession, trade_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    stmt = select(Trade).where(Trade.id == trade_id, Trade.user_id == user_id)
    result = await db.execute(stmt)
    db_obj = result.scalar_one_or_none()
    if not db_obj:
        return False
    await db.delete(db_obj)
    await db.commit()
    return True
