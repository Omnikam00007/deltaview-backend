import uuid
from datetime import date
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.database import get_db
from app.db.crud_analytics import get_user_ledger_entries
from app.models.user import User
from app.schemas.analytics import LedgerEntryResponse

router = APIRouter()


@router.get("/", response_model=List[LedgerEntryResponse])
async def list_ledger_entries(
    broker_account_id: uuid.UUID | None = Query(None),
    category: str | None = Query(None, description="deposit, withdrawal, charge, dividend, interest, other"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List ledger entries with optional filters."""
    return await get_user_ledger_entries(
        db, current_user.id,
        broker_account_id=broker_account_id,
        category=category,
        start_date=start_date,
        end_date=end_date,
    )
