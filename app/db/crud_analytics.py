import uuid
from datetime import date
from typing import Sequence

from sqlalchemy import select
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


# --------------- Daily Portfolio Snapshot ---------------

async def create_portfolio_snapshot(db: AsyncSession, user_id: uuid.UUID, obj_in: PortfolioSnapshotCreate) -> DailyPortfolioSnapshot:
    db_obj = DailyPortfolioSnapshot(user_id=user_id, **obj_in.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def compute_and_save_snapshots(db: AsyncSession) -> int:
    """Computes daily snapshot (total value, equity, cash) for all users and saves it."""
    from sqlalchemy import func
    from datetime import date
    from app.models.holding import Holding
    
    # 1. Get all users
    # We do a basic select of distinct user_ids from either holdings or funds_balance
    stmt_users = select(FundsBalance.user_id).distinct()
    res_users = await db.execute(stmt_users)
    user_ids = res_users.scalars().all()
    
    today = date.today()
    created_count = 0
    
    for u_id in user_ids:
        # Calculate Cash Balance
        stmt_cash = select(
            func.sum(FundsBalance.withdrawable_balance + FundsBalance.unsettled_credits).label("total_cash")
        ).where(FundsBalance.user_id == u_id)
        res_cash = await db.execute(stmt_cash)
        total_cash = float(res_cash.scalar() or 0.0)
        
        # Calculate Holdings Value
        stmt_hold = select(
            func.sum(Holding.current_value).label("equity_value"),
            func.sum(Holding.quantity * Holding.avg_cost).label("invested")
        ).where(Holding.user_id == u_id)
        res_hold = await db.execute(stmt_hold)
        row = res_hold.one_or_none()
        equity_val = float(row.equity_value if row and row.equity_value else 0.0)
        invest_val = float(row.invested if row and row.invested else 0.0)
        
        # Snapshot row
        # (Using Postgres insert to handle 'on_conflict_do_update' for idempotent daily runs)
        from sqlalchemy.dialects.postgresql import insert
        
        values = {
            "id": uuid.uuid4(),
            "user_id": u_id,
            "snapshot_date": today,
            "total_value": total_cash + equity_val,
            "equity_value": equity_val,
            "cash_balance": total_cash,
        }
        
        stmt = insert(DailyPortfolioSnapshot).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "snapshot_date"],
            set_= {
                "total_value": stmt.excluded.total_value,
                "equity_value": stmt.excluded.equity_value,
                "cash_balance": stmt.excluded.cash_balance,
            }
        )
        await db.execute(stmt)
        created_count += 1
        
    await db.commit()
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

