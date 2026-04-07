import uuid
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.database import get_db
from app.db.crud_analytics import (
    create_daily_pnl, get_user_daily_pnl, backfill_daily_pnl,
    create_portfolio_snapshot, get_user_portfolio_snapshots,
    create_realized_pnl, get_user_realized_pnl,
    get_user_tax_summary,
)
from app.models.user import User
from app.schemas.analytics import (
    DailyPnlCreate, DailyPnlResponse,
    PortfolioSnapshotCreate, PortfolioSnapshotResponse,
    RealizedPnlCreate, RealizedPnlResponse,
    TaxSummaryResponse,
)
from pydantic import BaseModel

class LivePortfolioSummary(BaseModel):
    total_value: float
    equity_value: float
    cash_value: float
    total_invested: float
    total_pnl: float

router = APIRouter()

@router.get("/portfolio-live-summary", response_model=LivePortfolioSummary)
async def get_portfolio_live_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate live Holdings value and Cash balances for the Dashboard header."""
    from sqlalchemy import func
    from app.models.holding import Holding
    from app.models.funds_balance import FundsBalance
    
    stmt_cash = select(
        func.sum(FundsBalance.withdrawable_balance + FundsBalance.unsettled_credits)
    ).where(FundsBalance.user_id == current_user.id)
    res_cash = await db.execute(stmt_cash)
    total_cash = float(res_cash.scalar() or 0.0)
    
    stmt_hold = select(
        func.sum(Holding.current_value).label("equity_value"),
        func.sum(Holding.quantity * Holding.avg_cost).label("invested"),
        func.sum(Holding.pnl).label("pnl")
    ).where(Holding.user_id == current_user.id)
    res_hold = await db.execute(stmt_hold)
    row = res_hold.one_or_none()
    
    equity_val = float(row.equity_value if row and row.equity_value else 0.0)
    invest_val = float(row.invested if row and row.invested else 0.0)
    pnl_val = float(row.pnl if row and row.pnl else 0.0)
    
    return LivePortfolioSummary(
        total_value=total_cash + equity_val,
        equity_value=equity_val,
        cash_value=total_cash,
        total_invested=invest_val,
        total_pnl=pnl_val
    )

# --------------- Daily P&L ---------------

@router.post("/daily-pnl", response_model=DailyPnlResponse, status_code=status.HTTP_201_CREATED)
async def add_daily_pnl(
    body: DailyPnlCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record daily P&L entry."""
    return await create_daily_pnl(db, current_user.id, body)


@router.get("/daily-pnl", response_model=List[DailyPnlResponse])
async def list_daily_pnl(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    segment: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List daily P&L entries with optional filters."""
    return await get_user_daily_pnl(db, current_user.id, start_date=start_date, end_date=end_date, segment=segment)


@router.post("/daily-pnl/backfill")
async def backfill_daily_pnl_endpoint(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recompute all daily P&L rows from historical trades for the current user."""
    count = await backfill_daily_pnl(db, current_user.id)
    return {"status": "ok", "rows_upserted": count}


class DateRange(BaseModel):
    start_date: date
    end_date: date

@router.post("/snapshots/backfill")
async def backfill_snapshots_endpoint(
    body: DateRange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.db.crud_analytics import backfill_portfolio_snapshots
    count = await backfill_portfolio_snapshots(db, current_user.id, body.start_date, body.end_date)
    return {"status": "ok", "rows_upserted": count}

# --------------- Portfolio Snapshots ---------------

@router.post("/snapshots", response_model=PortfolioSnapshotResponse, status_code=status.HTTP_201_CREATED)
async def add_portfolio_snapshot(
    body: PortfolioSnapshotCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a daily portfolio snapshot."""
    return await create_portfolio_snapshot(db, current_user.id, body)


@router.get("/snapshots", response_model=List[PortfolioSnapshotResponse])
async def list_portfolio_snapshots(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List portfolio snapshots for charting portfolio growth over time."""
    return await get_user_portfolio_snapshots(db, current_user.id, start_date=start_date, end_date=end_date)


# --------------- Realized P&L ---------------

@router.post("/realized-pnl", response_model=RealizedPnlResponse, status_code=status.HTTP_201_CREATED)
async def add_realized_pnl(
    body: RealizedPnlCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a realized P&L entry from a closed position."""
    return await create_realized_pnl(db, current_user.id, body)


@router.get("/realized-pnl", response_model=List[RealizedPnlResponse])
async def list_realized_pnl(
    instrument_id: uuid.UUID | None = Query(None),
    tax_category: str | None = Query(None, description="STCG or LTCG"),
    financial_year: str | None = Query(None, description="e.g. 2025-26"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List realized P&L entries with tax and date filters."""
    return await get_user_realized_pnl(
        db, current_user.id,
        instrument_id=instrument_id,
        tax_category=tax_category,
        financial_year=financial_year,
        start_date=start_date,
        end_date=end_date,
    )


# --------------- Tax Summary ---------------

@router.get("/tax-summary", response_model=TaxSummaryResponse)
async def get_tax_summary(
    financial_year: str | None = Query(None, description="e.g. 2025-26"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated STCG/LTCG tax breakdown for a financial year."""
    return await get_user_tax_summary(db, current_user.id, financial_year=financial_year)
