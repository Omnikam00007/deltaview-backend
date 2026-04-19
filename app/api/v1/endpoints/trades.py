import uuid
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.database import get_db
from app.db.crud_trade import create_trade, delete_trade, get_trade_by_id, get_user_trades, InsufficientHoldingError, InsufficientFundsError
from app.models.user import User
from app.schemas.trade import TradeCreate, TradeResponse

router = APIRouter()


@router.post("/", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
async def add_trade(
    body: TradeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a new trade."""
    if body.trade_type.upper() not in ("BUY", "SELL"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="trade_type must be 'BUY' or 'SELL'")
    
    try:
        return await create_trade(db, current_user.id, body)
    except (InsufficientHoldingError, InsufficientFundsError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=List[TradeResponse])
async def list_trades(
    broker_account_id: uuid.UUID | None = Query(None),
    instrument_id: uuid.UUID | None = Query(None),
    trade_type: str | None = Query(None, description="BUY or SELL"),
    segment: str | None = Query(None, description="equity, fno, mf, etc."),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List trades with optional filters."""
    return await get_user_trades(
        db, current_user.id,
        broker_account_id=broker_account_id,
        instrument_id=instrument_id,
        trade_type=trade_type,
        segment=segment,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(
    trade_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific trade by ID."""
    trade = await get_trade_by_id(db, trade_id, current_user.id)
    if not trade:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    return trade


@router.put("/{trade_id}", response_model=TradeResponse)
async def update_trade_endpoint(
    trade_id: uuid.UUID,
    body: dict,
    version: int = Query(..., description="Concurrent modification version lock"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a trade."""
    from app.db.crud_trade import update_trade
    try:
        return await update_trade(db, trade_id, current_user.id, version, body)
    except NotImplementedError:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Ledger rewriting requires complex FIFO reversal")


@router.delete("/{trade_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_trade(
    trade_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a trade."""
    success = await delete_trade(db, trade_id, current_user.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
