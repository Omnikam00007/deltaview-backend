import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.database import get_db
from app.db.crud_broker_account import create_broker_account, delete_broker_account, get_user_broker_accounts
from app.models.user import User
from app.schemas.broker_account import BrokerAccountCreate, BrokerAccountResponse

router = APIRouter()


@router.post("/", response_model=BrokerAccountResponse, status_code=status.HTTP_201_CREATED)
async def add_broker_account(
    body: BrokerAccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add a new broker account connection for the current user."""
    return await create_broker_account(db, current_user.id, body)


@router.get("/", response_model=List[BrokerAccountResponse])
async def list_broker_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all broker accounts for the current user."""
    return await get_user_broker_accounts(db, current_user.id)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_broker_account(
    account_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Disconnect a specific broker account."""
    success = await delete_broker_account(db, account_id, current_user.id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Broker account not found")
