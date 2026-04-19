import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.database import get_db
from app.db.crud_holding import (
    create_holding,
    bulk_sync_holdings,
    create_holding_tag,
    delete_holding,
    delete_holding_tag,
    get_holding_by_id,
    get_portfolio_summary,
    get_user_holding_tags,
    get_user_holdings,
    get_user_holdings_consolidated,
    update_holding,
)
from app.models.user import User
from app.schemas.holding import (
    ConsolidatedHoldingResponse,
    HoldingCreate,
    HoldingResponse,
    HoldingTagCreate,
    HoldingTagResponse,
    HoldingUpdate,
    PortfolioSummary,
)

router = APIRouter()


# --------------- Holdings ---------------

@router.post("/", response_model=HoldingResponse, status_code=status.HTTP_201_CREATED)
async def add_holding(
    body: HoldingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new holding to the portfolio AND automatically fetch its live price."""
    from app.db.crud_holding import refresh_unrealized_pnl
    
    # 1. Create the holding in the database
    holding = await create_holding(db, current_user.id, body)
    
    # 2. Immediately trigger price refresh for this user's holdings
    await refresh_unrealized_pnl(db, current_user.id)
    
    # 3. Reload the holding object to get the newly calculated P&L fields
    await db.refresh(holding, attribute_names=["instrument", "broker_account"])
    
    return holding


@router.post("/sync", response_model=dict, status_code=status.HTTP_200_OK)
async def sync_holdings(
    body: List[HoldingCreate],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk import or sync holdings (upserts based on user, broker, instrument)."""
    synced_count = await bulk_sync_holdings(db, current_user.id, body)
    return {"message": "success", "synced_count": synced_count}


@router.post("/refresh-prices", response_model=dict, status_code=status.HTTP_200_OK)
async def refresh_user_prices(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch latest prices from yfinance for the current user's holdings and update P&L."""
    from app.db.crud_holding import refresh_unrealized_pnl
    updated_count = await refresh_unrealized_pnl(db, current_user.id)
    return {"message": "success", "updated_count": updated_count}


@router.get("/")
async def list_holdings(
    broker_account_id: uuid.UUID | None = Query(None, description="Filter by broker account"),
    consolidated: bool = Query(True, description="Aggregate holdings by instrument across brokers"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all holdings for the current user.

    By default returns consolidated holdings (one row per stock, aggregated
    across broker accounts, zero-quantity positions excluded).
    Pass ?consolidated=false to get the raw per-lot rows.
    """
    if consolidated and not broker_account_id:
        return await get_user_holdings_consolidated(db, current_user.id)
    return await get_user_holdings(db, current_user.id, broker_account_id)


@router.get("/summary", response_model=PortfolioSummary)
async def portfolio_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated portfolio summary (total invested, current value, P&L)."""
    return await get_portfolio_summary(db, current_user.id)


@router.get("/{holding_id}", response_model=HoldingResponse)
async def get_holding(
    holding_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific holding by ID."""
    holding = await get_holding_by_id(db, holding_id, current_user.id)
    if not holding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")
    return holding


@router.patch("/{holding_id}", response_model=HoldingResponse)
async def patch_holding(
    holding_id: uuid.UUID,
    body: HoldingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a holding (e.g. after price sync)."""
    holding = await get_holding_by_id(db, holding_id, current_user.id)
    if not holding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")
    return await update_holding(db, holding, body)


@router.delete("/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_holding(
    holding_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a holding."""
    success = await delete_holding(db, holding_id, current_user.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")


# --------------- Holding Tags ---------------

@router.post("/tags", response_model=HoldingTagResponse, status_code=status.HTTP_201_CREATED)
async def add_holding_tag(
    body: HoldingTagCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Tag a holding/instrument (e.g. 'long-term', 'risky')."""
    return await create_holding_tag(db, current_user.id, body.instrument_id, body.tag_name)


@router.get("/tags/", response_model=List[HoldingTagResponse])
async def list_holding_tags(
    instrument_id: uuid.UUID | None = Query(None, description="Filter tags by instrument"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all user's holding tags, optionally filtered by instrument."""
    return await get_user_holding_tags(db, current_user.id, instrument_id)


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_holding_tag(
    tag_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a holding tag."""
    success = await delete_holding_tag(db, tag_id, current_user.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")
