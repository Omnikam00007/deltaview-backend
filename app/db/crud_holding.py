import uuid
from typing import Sequence

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.holding import Holding
from app.models.holding_tag import HoldingTag
from app.schemas.holding import HoldingCreate, HoldingUpdate
from sqlalchemy.dialects.postgresql import insert


from app.models.instrument import Instrument
import yfinance as yf
import asyncio


# --------------- Holdings ---------------

async def refresh_unrealized_pnl(db: AsyncSession, user_id: uuid.UUID | None = None) -> int:
    """Fetch latest prices from yfinance and update all holdings' unrealized P&L."""
    
    # 1. Get unique instruments for the target holdings
    stmt = select(Instrument).join(Holding, Holding.instrument_id == Instrument.id)
    if user_id:
        stmt = stmt.where(Holding.user_id == user_id)
        
    result = await db.execute(stmt)
    instruments = result.scalars().unique().all()
    
    if not instruments:
        return 0
        
    # Map instrument id to symbol
    inst_map = {i.id: i for i in instruments}
    
    # Format symbols for yfinance (append .NS if needed for Indian stocks)
    yf_symbols = []
    symbol_to_id = {}
    for i in instruments:
        sym = f"{i.symbol}.NS" if "." not in i.symbol else i.symbol
        yf_symbols.append(sym)
        symbol_to_id[sym] = i.id
        
    # 2. Fetch bulk prices from yfinance (this is a blocking network call, should ideally run in threadpool)
    def fetch_prices():
        tickers = yf.Tickers(" ".join(yf_symbols))
        prices = {}
        for sym in yf_symbols:
            try:
                info = tickers.tickers[sym].info
                # Try getting regularMarketPrice or previousClose
                price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
                if price:
                    prices[sym] = price
            except Exception:
                pass
        return prices
    
    loop = asyncio.get_running_loop()
    live_prices = await loop.run_in_executor(None, fetch_prices)
    
    if not live_prices:
        return 0
        
    # 3. Update holdings
    stmt_holdings = select(Holding)
    if user_id:
        stmt_holdings = stmt_holdings.where(Holding.user_id == user_id)
    
    result_holdings = await db.execute(stmt_holdings)
    holdings = result_holdings.scalars().all()
    
    updated_count = 0
    for h in holdings:
        inst = inst_map.get(h.instrument_id)
        if not inst:
            continue
            
        sym = f"{inst.symbol}.NS" if "." not in inst.symbol else inst.symbol
        latest_price = live_prices.get(sym)
        
        if latest_price:
            h.ltp = latest_price
            h.current_value = float(h.quantity) * latest_price
            h.pnl = h.current_value - (float(h.quantity) * float(h.avg_cost))
            if h.quantity > 0 and h.avg_cost > 0:
                invested = float(h.quantity) * float(h.avg_cost)
                h.pnl_percent = (h.pnl / invested) * 100
            else:
                h.pnl_percent = 0.0
            updated_count += 1
            
    await db.commit()
    return updated_count

async def create_holding(db: AsyncSession, user_id: uuid.UUID, obj_in: HoldingCreate) -> Holding:
    db_obj = Holding(
        user_id=user_id,
        broker_account_id=obj_in.broker_account_id,
        instrument_id=obj_in.instrument_id,
        quantity=obj_in.quantity,
        avg_cost=obj_in.avg_cost,
        ltp=obj_in.ltp,
        current_value=obj_in.current_value,
        pnl=obj_in.pnl,
        pnl_percent=obj_in.pnl_percent,
        as_of_date=obj_in.as_of_date,
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj, attribute_names=["instrument", "broker_account"])
    return db_obj


async def bulk_sync_holdings(db: AsyncSession, user_id: uuid.UUID, holdings_in: Sequence[HoldingCreate]) -> int:
    """Bulk upsert holdings using Postgres ON CONFLICT DO UPDATE."""
    if not holdings_in:
        return 0

    values = []
    for h in holdings_in:
        values.append({
            "id": uuid.uuid4(),
            "user_id": user_id,
            "broker_account_id": h.broker_account_id,
            "instrument_id": h.instrument_id,
            "quantity": h.quantity,
            "avg_cost": h.avg_cost,
            "ltp": h.ltp,
            "current_value": h.current_value,
            "pnl": h.pnl,
            "pnl_percent": h.pnl_percent,
            "as_of_date": h.as_of_date,
        })

    stmt = insert(Holding).values(values)
    
    # On conflict on (user_id, broker_account_id, instrument_id), update the specific fields
    update_dict = {
        "quantity": stmt.excluded.quantity,
        "avg_cost": stmt.excluded.avg_cost,
        "ltp": stmt.excluded.ltp,
        "current_value": stmt.excluded.current_value,
        "pnl": stmt.excluded.pnl,
        "pnl_percent": stmt.excluded.pnl_percent,
        "as_of_date": stmt.excluded.as_of_date,
        "updated_at": func.now()
    }
    
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "broker_account_id", "instrument_id"],
        set_=update_dict
    )
    
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount


async def get_user_holdings(
    db: AsyncSession,
    user_id: uuid.UUID,
    broker_account_id: uuid.UUID | None = None,
) -> Sequence[Holding]:
    stmt = (
        select(Holding)
        .where(Holding.user_id == user_id)
        .options(selectinload(Holding.instrument), selectinload(Holding.broker_account))
        .order_by(Holding.updated_at.desc())
    )
    if broker_account_id:
        stmt = stmt.where(Holding.broker_account_id == broker_account_id)
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_holding_by_id(db: AsyncSession, holding_id: uuid.UUID, user_id: uuid.UUID) -> Holding | None:
    stmt = (
        select(Holding)
        .where(Holding.id == holding_id, Holding.user_id == user_id)
        .options(selectinload(Holding.instrument), selectinload(Holding.broker_account))
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_holding(db: AsyncSession, db_obj: Holding, obj_in: HoldingUpdate) -> Holding:
    update_data = obj_in.model_dump(exclude_unset=True)

    # ── Capture old invested amount before applying changes ──
    old_qty = float(db_obj.quantity)
    old_avg = float(db_obj.avg_cost)
    old_invested = old_qty * old_avg

    for field, value in update_data.items():
        setattr(db_obj, field, value)
    db.add(db_obj)

    # ── Compute new invested amount and delta ──
    new_qty = float(db_obj.quantity)
    new_avg = float(db_obj.avg_cost)
    new_invested = new_qty * new_avg
    delta = new_invested - old_invested          # +ve = more cash used, -ve = cash freed

    # ── Adjust FundsBalance if invested amount changed ──
    if abs(delta) > 0.01:                        # avoid floating-point noise
        from datetime import datetime, timezone
        from app.models.funds_balance import FundsBalance
        from app.models.ledger_entry import LedgerEntry

        stmt = (
            select(FundsBalance)
            .where(
                FundsBalance.user_id == db_obj.user_id,
                FundsBalance.broker_account_id == db_obj.broker_account_id,
            )
            .with_for_update()                   # row-level lock
        )
        result = await db.execute(stmt)
        balance = result.scalar_one_or_none()

        if balance:
            now = datetime.now(timezone.utc)

            # Deduct from available margin (or credit back)
            balance.available_margin = float(balance.available_margin) - delta
            balance.used_margin = float(balance.used_margin) + delta

            # Recompute total_margin
            balance.total_margin = (
                float(balance.available_margin)
                + float(balance.pledged_margin)
                + float(balance.used_margin)
            )
            balance.as_of = now

            # Create audit ledger entry
            if delta > 0:
                narration = f"Holding Update — ₹{delta:,.2f} deployed"
                entry_type = "debit"
            else:
                narration = f"Holding Update — ₹{abs(delta):,.2f} freed"
                entry_type = "credit"

            ledger = LedgerEntry(
                user_id=db_obj.user_id,
                broker_account_id=db_obj.broker_account_id,
                entry_date=now,
                narration=narration,
                original_narration="DeltaView holding_update",
                entry_type=entry_type,
                amount=abs(delta),
                closing_balance=float(balance.available_margin),
                category="holding_adjustment",
            )
            db.add(ledger)

    await db.commit()
    await db.refresh(db_obj, attribute_names=["instrument", "broker_account"])
    return db_obj


async def delete_holding(db: AsyncSession, holding_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    stmt = select(Holding).where(Holding.id == holding_id, Holding.user_id == user_id)
    result = await db.execute(stmt)
    db_obj = result.scalar_one_or_none()
    if not db_obj:
        return False
    await db.delete(db_obj)
    await db.commit()
    return True


async def get_portfolio_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    stmt = select(
        func.sum(Holding.quantity * Holding.avg_cost).label("total_invested"),
        func.sum(Holding.current_value).label("current_value"),
        func.sum(Holding.pnl).label("total_pnl"),
        func.count(Holding.id).label("holding_count"),
    ).where(Holding.user_id == user_id)
    result = await db.execute(stmt)
    row = result.one()

    total_invested = float(row.total_invested or 0)
    current_value = float(row.current_value or 0)
    total_pnl = float(row.total_pnl or 0)
    total_pnl_percent = (total_pnl / total_invested * 100) if total_invested else 0.0

    return {
        "total_invested": total_invested,
        "current_value": current_value,
        "total_pnl": total_pnl,
        "total_pnl_percent": round(total_pnl_percent, 4),
        "holding_count": row.holding_count,
    }


# --------------- Holding Tags ---------------

async def create_holding_tag(db: AsyncSession, user_id: uuid.UUID, instrument_id: uuid.UUID, tag_name: str) -> HoldingTag:
    db_obj = HoldingTag(user_id=user_id, instrument_id=instrument_id, tag_name=tag_name)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def get_user_holding_tags(db: AsyncSession, user_id: uuid.UUID, instrument_id: uuid.UUID | None = None) -> Sequence[HoldingTag]:
    stmt = select(HoldingTag).where(HoldingTag.user_id == user_id).order_by(HoldingTag.created_at.desc())
    if instrument_id:
        stmt = stmt.where(HoldingTag.instrument_id == instrument_id)
    result = await db.execute(stmt)
    return result.scalars().all()


async def delete_holding_tag(db: AsyncSession, tag_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    stmt = select(HoldingTag).where(HoldingTag.id == tag_id, HoldingTag.user_id == user_id)
    result = await db.execute(stmt)
    db_obj = result.scalar_one_or_none()
    if not db_obj:
        return False
    await db.delete(db_obj)
    await db.commit()
    return True
