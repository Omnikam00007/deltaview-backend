from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.database import get_db
from app.db.crud_fund_transaction import create_fund_transaction, get_user_fund_transactions, InsufficientBalanceError
from app.models.user import User
from app.schemas.fund_transaction import FundTransactionCreate, FundTransactionResponse

router = APIRouter()


@router.post("/", response_model=FundTransactionResponse, status_code=status.HTTP_201_CREATED)
async def initiate_fund_transaction(
    body: FundTransactionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Initiate a new fund transaction (deposit or withdrawal)."""
    if body.transaction_type not in ["add", "withdraw"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transaction type must be 'add' or 'withdraw'")
    if body.amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be greater than zero")

    try:
        return await create_fund_transaction(db, current_user.id, body)
    except InsufficientBalanceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=List[FundTransactionResponse])
async def list_fund_transactions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all fund transactions for the current user (Ledger view)."""
    return await get_user_fund_transactions(db, current_user.id)
