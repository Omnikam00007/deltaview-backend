import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_account import BankAccount
from app.schemas.bank_account import BankAccountCreate


async def create_bank_account(db: AsyncSession, user_id: uuid.UUID, obj_in: BankAccountCreate) -> BankAccount:
    acc_num = obj_in.account_number
    # Basic masking, keeping only last 4 digits visible
    masked = f"{"X" * max(len(acc_num) - 4, 4)}{acc_num[-4:]}" if len(acc_num) > 4 else acc_num
    
    # If this account is set to primary, we should probably unset other primaries.
    # We will just mark it here and let DB enforce it if needed.
    
    db_obj = BankAccount(
        user_id=user_id,
        bank_name=obj_in.bank_name,
        account_number=masked,
        ifsc_code=obj_in.ifsc_code,
        is_primary=obj_in.is_primary,
        is_verified=False
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def get_user_bank_accounts(db: AsyncSession, user_id: uuid.UUID) -> Sequence[BankAccount]:
    stmt = select(BankAccount).where(BankAccount.user_id == user_id).order_by(BankAccount.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


async def delete_bank_account(db: AsyncSession, account_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    stmt = select(BankAccount).where(BankAccount.id == account_id, BankAccount.user_id == user_id)
    result = await db.execute(stmt)
    db_obj = result.scalar_one_or_none()
    if not db_obj:
        return False
    await db.delete(db_obj)
    await db.commit()
    return True
