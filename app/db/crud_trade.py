import uuid
from datetime import date
from typing import Sequence

from sqlalchemy import func, select, exc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.trade import Trade
from app.models.holding import Holding
from app.models.holding_lot import HoldingLot
from app.models.cash_transaction import CashTransaction
from app.schemas.trade import TradeCreate
from app.engine.pnl_engine import process_fifo_sell, compute_daily_total_pnl


class InsufficientHoldingError(ValueError):
    pass


class InsufficientFundsError(ValueError):
    pass


class ConcurrentModificationError(ValueError):
    pass


async def _verify_and_update_cash(db: AsyncSession, user_id: uuid.UUID, amount: float, trade_id: uuid.UUID, txn_type: str, timestamp):
    """Creates a CashTransaction. For BUYs, checks if funds are sufficient first."""
    if amount < 0:
        # Checking sufficient balance
        cash_stmt = select(func.coalesce(func.sum(CashTransaction.amount), 0)).where(CashTransaction.user_id == user_id)
        current_cash = float((await db.execute(cash_stmt)).scalar() or 0.0)
        if current_cash + amount < 0:
            raise InsufficientFundsError(f"Insufficient funds. Required: {abs(amount)}, Available: {current_cash}")
            
    txn = CashTransaction(
        user_id=user_id,
        timestamp=timestamp,
        amount=amount,
        trade_id=trade_id,
        transaction_type=txn_type
    )
    db.add(txn)


async def create_trade(db: AsyncSession, user_id: uuid.UUID, obj_in: TradeCreate) -> Trade:
    """Create a trade, matching FIFO blocks, enforcing Cash flows, updating DailyPnl."""
    
    # 1. Enforce Trade constraints & Lock Holding
    stmt_h = (
        select(Holding)
        .where(
            Holding.user_id == user_id,
            Holding.broker_account_id == obj_in.broker_account_id,
            Holding.instrument_id == obj_in.instrument_id,
        )
        .with_for_update()  # Row lock to prevent race geometry
    )
    res_h = await db.execute(stmt_h)
    holding = res_h.scalar_one_or_none()
    
    if obj_in.trade_type.upper() == "SELL":
        if not holding or float(holding.quantity) < float(obj_in.quantity):
            raise InsufficientHoldingError(f"Cannot sell {obj_in.quantity}. Available: {float(holding.quantity) if holding else 0}")
    
    # 2. Add Trade
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
        version=1
    )
    db.add(db_obj)
    await db.flush()
    
    # 3. Cash Management
    cash_delta = -float(obj_in.trade_value) if db_obj.trade_type == "BUY" else float(obj_in.trade_value)
    await _verify_and_update_cash(db, user_id, cash_delta, db_obj.id, f"{db_obj.trade_type}_EXECUTION", db_obj.trade_date)
    
    # 4. Holding & FIFO Management
    if db_obj.trade_type == "BUY":
        # Create Holding Lot
        lot = HoldingLot(
            holding_id=holding.id if holding else uuid.uuid4(), # Holding id must exist, so we create holding strictly before or flush
            instrument_id=db_obj.instrument_id,
            user_id=user_id,
            trade_id=db_obj.id,
            quantity=db_obj.quantity,
            avg_cost=db_obj.price,
        )
        
        if holding:
            new_qty = float(holding.quantity) + float(db_obj.quantity)
            new_cost = ((float(holding.quantity) * float(holding.avg_cost)) + (float(db_obj.quantity) * float(db_obj.price))) / new_qty
            holding.quantity = new_qty
            holding.avg_cost = new_cost
            lot.holding_id = holding.id
        else:
            holding = Holding(
                user_id=user_id,
                broker_account_id=db_obj.broker_account_id,
                instrument_id=db_obj.instrument_id,
                quantity=db_obj.quantity,
                avg_cost=db_obj.price,
                as_of_date=db_obj.trade_date,
            )
            db.add(holding)
            await db.flush()
            lot.holding_id = holding.id
            
        db.add(lot)
        
    elif db_obj.trade_type == "SELL":
        # Deduct holding quantity
        holding.quantity = float(holding.quantity) - float(db_obj.quantity)
        
        # FIFO Process
        await process_fifo_sell(
            db=db,
            user_id=user_id,
            broker_account_id=db_obj.broker_account_id,
            instrument_id=db_obj.instrument_id,
            sell_qty=float(db_obj.quantity),
            sell_price=float(db_obj.price),
            sell_trade_id=db_obj.id,
            sell_date=db_obj.trade_date
        )
        
    holding.as_of_date = db_obj.trade_date

    # 5. EOD Engine Call
    await compute_daily_total_pnl(db, user_id, db_obj.trade_date)
    
    await db.commit()
    await db.refresh(db_obj, attribute_names=["instrument", "broker_account"])
    return db_obj


async def update_trade(db: AsyncSession, trade_id: uuid.UUID, user_id: uuid.UUID, version: int, obj_in: dict) -> Trade:
    """Updating a trade natively requires rolling back previous trade state via complete delete & recreate."""
    raise NotImplementedError("Direct update not supported natively without full ledger reversal.")


async def delete_trade(db: AsyncSession, trade_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Strictly deletes a trade. If a SELL, it will theoretically require FIFO unmatching. 
    A full robust implementation in Phase 8 will re-run the ledger pipeline entirely for safety."""
    stmt = select(Trade).where(Trade.id == trade_id, Trade.user_id == user_id)
    result = await db.execute(stmt)
    db_obj = result.scalar_one_or_none()
    if not db_obj:
        return False
        
    await db.delete(db_obj)
    await db.commit()
    return True


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
