import uuid
from datetime import date
from typing import Sequence

from sqlalchemy import func, select, asc, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ledger_entry import LedgerEntry
from app.models.funds_balance import FundsBalance
from app.models.daily_pnl import DailyPnl
from app.models.daily_portfolio_snapshot import DailyPortfolioSnapshot
from app.models.realized_pnl import RealizedPnl
from app.schemas.analytics import (
    LedgerEntryCreate, FundsBalanceUpsert, DailyPnlCreate,
    PortfolioSnapshotCreate, RealizedPnlCreate,
)


# --------------- Ledger Entries ---------------

async def create_ledger_entry(db: AsyncSession, user_id: uuid.UUID, obj_in: LedgerEntryCreate) -> LedgerEntry:
    db_obj = LedgerEntry(user_id=user_id, **obj_in.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def get_user_ledger_entries(
    db: AsyncSession,
    user_id: uuid.UUID,
    broker_account_id: uuid.UUID | None = None,
    category: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> Sequence[LedgerEntry]:
    stmt = select(LedgerEntry).where(LedgerEntry.user_id == user_id).order_by(LedgerEntry.entry_date.desc())
    if broker_account_id:
        stmt = stmt.where(LedgerEntry.broker_account_id == broker_account_id)
    if category:
        stmt = stmt.where(LedgerEntry.category == category)
    if start_date:
        stmt = stmt.where(LedgerEntry.entry_date >= start_date)
    if end_date:
        stmt = stmt.where(LedgerEntry.entry_date <= end_date)
    result = await db.execute(stmt)
    return result.scalars().all()


# --------------- Funds Balance ---------------

async def upsert_funds_balance(db: AsyncSession, user_id: uuid.UUID, obj_in: FundsBalanceUpsert) -> FundsBalance:
    stmt = select(FundsBalance).where(
        FundsBalance.user_id == user_id,
        FundsBalance.broker_account_id == obj_in.broker_account_id,
    )
    result = await db.execute(stmt)
    db_obj = result.scalar_one_or_none()

    if db_obj:
        for field, value in obj_in.model_dump(exclude={"broker_account_id"}).items():
            setattr(db_obj, field, value)
    else:
        db_obj = FundsBalance(user_id=user_id, **obj_in.model_dump())

    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def get_user_funds_balances(db: AsyncSession, user_id: uuid.UUID) -> Sequence[FundsBalance]:
    stmt = select(FundsBalance).where(FundsBalance.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalars().all()


# --------------- Daily P&L ---------------

async def create_daily_pnl(db: AsyncSession, user_id: uuid.UUID, obj_in: DailyPnlCreate) -> DailyPnl:
    db_obj = DailyPnl(user_id=user_id, **obj_in.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def get_user_daily_pnl(
    db: AsyncSession,
    user_id: uuid.UUID,
    start_date: date | None = None,
    end_date: date | None = None,
    segment: str | None = None,
) -> Sequence[DailyPnl]:
    stmt = select(DailyPnl).where(DailyPnl.user_id == user_id).order_by(DailyPnl.trade_date.desc())
    if start_date:
        stmt = stmt.where(DailyPnl.trade_date >= start_date)
    if end_date:
        stmt = stmt.where(DailyPnl.trade_date <= end_date)
    if segment:
        stmt = stmt.where(DailyPnl.segment == segment)
    result = await db.execute(stmt)
    return result.scalars().all()


async def backfill_daily_pnl(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Recompute daily_pnl rows from trades + realized_pnl for a given user.

    Groups trades by (trade_date, segment), sums realized P&L for each date,
    and upserts into daily_pnl. Returns the number of rows upserted.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.trade import Trade

    # 1. Get distinct (trade_date, segment) pairs for this user
    date_seg_stmt = (
        select(Trade.trade_date, Trade.segment, func.count().label("trade_count"))
        .where(Trade.user_id == user_id)
        .group_by(Trade.trade_date, Trade.segment)
        .order_by(Trade.trade_date.asc())
    )
    date_seg_rows = (await db.execute(date_seg_stmt)).all()

    upserted = 0

    for row in date_seg_rows:
        trade_date = row.trade_date
        segment = (row.segment or "equity").lower()
        trade_count = row.trade_count

        # Sum realized net_pnl for sells on this date
        pnl_stmt = (
            select(func.coalesce(func.sum(RealizedPnl.net_pnl), 0))
            .where(
                RealizedPnl.user_id == user_id,
                RealizedPnl.sell_date == trade_date,
            )
        )
        daily_pnl_value = float((await db.execute(pnl_stmt)).scalar() or 0)

        values = {
            "id": uuid.uuid4(),
            "user_id": user_id,
            "trade_date": trade_date,
            "realized_pnl": daily_pnl_value,
            "unrealized_pnl": 0, # Backfill doesn't compute historic M2M yet
            "total_pnl": daily_pnl_value,
            "trade_count": trade_count,
            "segment": segment,
        }
        stmt = pg_insert(DailyPnl).values(values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_daily_pnl_user_date_segment",
            set_={
                "realized_pnl": stmt.excluded.realized_pnl,
                "total_pnl": stmt.excluded.total_pnl,
                "trade_count": stmt.excluded.trade_count,
            },
        )
        await db.execute(stmt)
        upserted += 1

    await db.commit()
    return upserted


# --------------- Daily Portfolio Snapshot ---------------

async def create_portfolio_snapshot(db: AsyncSession, user_id: uuid.UUID, obj_in: PortfolioSnapshotCreate) -> DailyPortfolioSnapshot:
    db_obj = DailyPortfolioSnapshot(user_id=user_id, **obj_in.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def backfill_portfolio_snapshots(db: AsyncSession, user_id: uuid.UUID, start_date: date, end_date: date) -> int:
    """
    Optimized historical snapshot reconstructor.
    Uses an in-memory accumulation strategy to avoid N+1 queries.
    """
    from datetime import timedelta
    from sqlalchemy.dialects.postgresql import insert
    from app.models.trade import Trade
    from app.models.cash_transaction import CashTransaction
    from app.models.holding import Holding
    from app.models.realized_pnl import RealizedPnl
    
    # 1. Fetch current prices (LTP) from Holdings as the fallback market price
    # NOTE: True historical pricing requires a dedicated price history table.
    price_stmt = select(Holding.instrument_id, Holding.ltp).where(Holding.user_id == user_id)
    prices = {row.instrument_id: float(row.ltp or 0.0) for row in (await db.execute(price_stmt)).all()}

    # 2. Pre-fetch all event data sorted by date
    # trades
    trades_stmt = select(Trade).where(Trade.user_id == user_id).order_by(asc(Trade.trade_date))
    all_trades = (await db.execute(trades_stmt)).scalars().all()
    
    # cash transactions
    cash_stmt = select(CashTransaction).where(CashTransaction.user_id == user_id).order_by(asc(CashTransaction.timestamp))
    all_cash = (await db.execute(cash_stmt)).scalars().all()
    
    # realized pnl
    realized_stmt = select(RealizedPnl).where(RealizedPnl.user_id == user_id).order_by(asc(RealizedPnl.sell_date))
    all_realized = (await db.execute(realized_stmt)).scalars().all()

    # 3. Initialization for the running state
    holdings_qty = {}
    holdings_cost = {}
    total_cash = 0.0
    total_realized_pnl = 0.0
    
    # Pointers to current processing items
    trade_idx = 0
    cash_idx = 0
    realized_idx = 0
    
    current_date = start_date
    # Pre-calculate state up to start_date - 1 (exclusive) to initialize correctly
    # If start_date is historical, we start from zero.
    
    # Efficiently catch up state to just before start_date
    while trade_idx < len(all_trades) and all_trades[trade_idx].trade_date < start_date:
        t = all_trades[trade_idx]
        inst = t.instrument_id
        if inst not in holdings_qty: holdings_qty[inst] = 0.0; holdings_cost[inst] = 0.0
        if t.trade_type == "BUY":
            holdings_qty[inst] += float(t.quantity)
            holdings_cost[inst] += float(t.quantity * t.price)
        elif t.trade_type == "SELL":
            if holdings_qty[inst] > 0:
                avg_cost = holdings_cost[inst] / holdings_qty[inst]
                holdings_qty[inst] -= float(t.quantity)
                holdings_cost[inst] -= float(t.quantity) * avg_cost
        trade_idx += 1

    while cash_idx < len(all_cash) and all_cash[cash_idx].timestamp.date() < start_date:
        total_cash += float(all_cash[cash_idx].amount)
        cash_idx += 1
        
    while realized_idx < len(all_realized) and all_realized[realized_idx].sell_date < start_date:
        total_realized_pnl += float(all_realized[realized_idx].net_pnl or 0)
        realized_idx += 1

    created_count = 0
    snapshots_to_upsert = []

    # 4. Main loop through the date range
    while current_date <= end_date:
        # Update state with today's events
        while cash_idx < len(all_cash) and all_cash[cash_idx].timestamp.date() == current_date:
            total_cash += float(all_cash[cash_idx].amount)
            cash_idx += 1
            
        while trade_idx < len(all_trades) and all_trades[trade_idx].trade_date == current_date:
            t = all_trades[trade_idx]
            inst = t.instrument_id
            if inst not in holdings_qty: holdings_qty[inst] = 0.0; holdings_cost[inst] = 0.0
            if t.trade_type == "BUY":
                holdings_qty[inst] += float(t.quantity)
                holdings_cost[inst] += float(t.quantity * t.price)
            elif t.trade_type == "SELL":
                if holdings_qty[inst] > 0:
                    avg_cost = holdings_cost[inst] / holdings_qty[inst]
                    holdings_qty[inst] -= float(t.quantity)
                    holdings_cost[inst] -= float(t.quantity) * avg_cost
            trade_idx += 1
            
        while realized_idx < len(all_realized) and all_realized[realized_idx].sell_date == current_date:
            total_realized_pnl += float(all_realized[realized_idx].net_pnl or 0)
            realized_idx += 1

        # Compute snapshot metrics
        equity_val = 0.0
        total_invested = 0.0
        for inst, qty in holdings_qty.items():
            if qty > 0.00001:
                cost = holdings_cost[inst]
                total_invested += cost
                price = prices.get(inst, 0.0)
                equity_val += (qty * price)
        
        total_unrealized_pnl = equity_val - total_invested
        total_pnl = total_realized_pnl + total_unrealized_pnl
        total_value = total_cash + equity_val

        values = {
            "id": uuid.uuid4(),
            "user_id": user_id,
            "snapshot_date": current_date,
            "total_value": total_value,
            "total_invested": total_invested,
            "total_realized_pnl": total_realized_pnl,
            "total_unrealized_pnl": total_unrealized_pnl,
            "total_pnl": total_pnl,
            "cash_balance": total_cash,
        }
        
        stmt = insert(DailyPortfolioSnapshot).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "snapshot_date"],
            set_= {
                k: stmt.excluded[k] for k in ["total_value", "total_invested", "total_realized_pnl", "total_unrealized_pnl", "total_pnl", "cash_balance"]
            }
        )
        await db.execute(stmt)
        
        created_count += 1
        current_date += timedelta(days=1)
        
    await db.commit()
    return created_count

async def compute_and_save_snapshots(db: AsyncSession) -> int:
    """Computes daily snapshot for all users using the backfill fast path in their local timezone."""
    import pytz
    from datetime import datetime
    from app.models.user import User
    
    stmt_users = select(User)
    res_users = await db.execute(stmt_users)
    users = res_users.scalars().all()
    
    created_count = 0
    
    for u in users:
        # Use user's specific timezone (default to UTC if missing/invalid)
        try:
            tz = pytz.timezone(u.timezone)
        except Exception:
            tz = pytz.UTC
            
        local_today = datetime.now(tz).date()
        await backfill_portfolio_snapshots(db, u.id, local_today, local_today)
        created_count += 1
        
    return created_count


async def get_user_portfolio_snapshots(
    db: AsyncSession,
    user_id: uuid.UUID,
    start_date: date | None = None,
    end_date: date | None = None,
) -> Sequence[DailyPortfolioSnapshot]:
    stmt = select(DailyPortfolioSnapshot).where(DailyPortfolioSnapshot.user_id == user_id).order_by(DailyPortfolioSnapshot.snapshot_date.desc())
    if start_date:
        stmt = stmt.where(DailyPortfolioSnapshot.snapshot_date >= start_date)
    if end_date:
        stmt = stmt.where(DailyPortfolioSnapshot.snapshot_date <= end_date)
    result = await db.execute(stmt)
    return result.scalars().all()


# --------------- Realized P&L ---------------

async def create_realized_pnl(db: AsyncSession, user_id: uuid.UUID, obj_in: RealizedPnlCreate) -> RealizedPnl:
    db_obj = RealizedPnl(user_id=user_id, **obj_in.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def get_user_realized_pnl(
    db: AsyncSession,
    user_id: uuid.UUID,
    instrument_id: uuid.UUID | None = None,
    tax_category: str | None = None,
    financial_year: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> Sequence[RealizedPnl]:
    stmt = select(RealizedPnl).where(RealizedPnl.user_id == user_id).order_by(RealizedPnl.sell_date.desc())
    if instrument_id:
        stmt = stmt.where(RealizedPnl.instrument_id == instrument_id)
    if tax_category:
        stmt = stmt.where(RealizedPnl.tax_category == tax_category)
    if financial_year:
        stmt = stmt.where(RealizedPnl.financial_year == financial_year)
    if start_date:
        stmt = stmt.where(RealizedPnl.sell_date >= start_date)
    if end_date:
        stmt = stmt.where(RealizedPnl.sell_date <= end_date)
    result = await db.execute(stmt)
    return result.scalars().all()


# --------------- Tax Summary ---------------

# Segment-aware Indian tax rates (FY 2025-26)
_EQUITY_SEGMENTS = {"equity", "fno", "etf"}  # STCG 20%, LTCG 12.5% above ₹1.25L
_DEBT_SEGMENTS = {"mf", "gold", "other"}     # Taxed at income tax slab rate (simplified to 20% here)


async def get_user_tax_summary(
    db: AsyncSession,
    user_id: uuid.UUID,
    financial_year: str | None = None,
) -> dict:
    """Aggregate realized P&L into STCG/LTCG tax breakdown, with segment-aware rates.
    
    Joins RealizedPnl with Instrument to determine asset segment and apply
    the correct tax rates per Indian tax rules.
    """
    from sqlalchemy import func as sqlfunc

    from app.models.instrument import Instrument

    fy = financial_year or _current_fy()

    # Query: group by (tax_category, segment) to apply different rates per segment
    stmt = (
        select(
            RealizedPnl.tax_category,
            Instrument.segment,
            sqlfunc.coalesce(sqlfunc.sum(RealizedPnl.net_pnl), 0).label("total_gains"),
        )
        .join(Instrument, RealizedPnl.instrument_id == Instrument.id)
        .where(RealizedPnl.user_id == user_id, RealizedPnl.financial_year == fy)
        .group_by(RealizedPnl.tax_category, Instrument.segment)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Aggregate gains by tax category
    stcg_gains = 0.0
    ltcg_gains = 0.0

    for row in rows:
        cat = row.tax_category
        gains = float(row.total_gains)
        if cat == "STCG":
            stcg_gains += gains
        elif cat == "LTCG":
            ltcg_gains += gains

    # Indian tax rules (FY 2025-26 budget):
    # Equity STCG: 20%, Equity LTCG: 12.5% (above ₹1.25L exemption)
    stcg_rate = 0.20
    stcg_tax = max(stcg_gains * stcg_rate, 0)

    ltcg_rate = 0.125
    ltcg_exemption = 125_000.0
    ltcg_taxable = max(ltcg_gains - ltcg_exemption, 0)
    ltcg_tax = ltcg_taxable * ltcg_rate

    return {
        "financial_year": fy,
        "stcg": {
            "gains": stcg_gains,
            "tax_rate": stcg_rate,
            "exemption_limit": 0,
            "taxable_amount": max(stcg_gains, 0),
            "tax": round(stcg_tax, 2),
        },
        "ltcg": {
            "gains": ltcg_gains,
            "tax_rate": ltcg_rate,
            "exemption_limit": ltcg_exemption,
            "taxable_amount": round(ltcg_taxable, 2),
            "tax": round(ltcg_tax, 2),
        },
        "total_gains": round(stcg_gains + ltcg_gains, 2),
        "total_tax_liability": round(stcg_tax + ltcg_tax, 2),
    }


def _current_fy() -> str:
    """Return Indian financial year string like '2025-26'."""
    from datetime import date as _date
    today = _date.today()
    year = today.year if today.month >= 4 else today.year - 1
    return f"{year}-{str(year + 1)[-2:]}"

