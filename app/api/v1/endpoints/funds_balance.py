from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.database import get_db
from app.db.crud_analytics import upsert_funds_balance, get_user_funds_balances
from app.models.user import User
from app.schemas.analytics import FundsBalanceUpsert, FundsBalanceResponse

router = APIRouter()


@router.put("/", response_model=FundsBalanceResponse, deprecated=True)
async def sync_funds_balance(
    body: FundsBalanceUpsert,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upsert funds balance for a broker account (one record per broker).
    
    DEPRECATED: This endpoint is for initial broker data import only.
    Use POST /fund-transactions/ for deposits and withdrawals.
    """
    return await upsert_funds_balance(db, current_user.id, body)


@router.get("/", response_model=List[FundsBalanceResponse])
async def list_funds_balances(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get funds balances for all broker accounts."""
    return await get_user_funds_balances(db, current_user.id)
