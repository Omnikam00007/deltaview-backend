import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.database import get_db
from app.db.crud_bank_account import create_bank_account, delete_bank_account, get_user_bank_accounts
from app.models.user import User
from app.schemas.bank_account import BankAccountCreate, BankAccountResponse

router = APIRouter()


@router.post("/", response_model=BankAccountResponse, status_code=status.HTTP_201_CREATED)
async def add_bank_account(
    body: BankAccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a new bank account for the current user."""
    return await create_bank_account(db, current_user.id, body)


@router.get("/", response_model=List[BankAccountResponse])
async def list_bank_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all bank accounts for the current user."""
    return await get_user_bank_accounts(db, current_user.id)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_bank_account(
    account_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a specific bank account belonging to the current user."""
    success = await delete_bank_account(db, account_id, current_user.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bank account not found")
