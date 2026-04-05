import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broker_account import BrokerAccount
from app.schemas.broker_account import BrokerAccountCreate


async def create_broker_account(db: AsyncSession, user_id: uuid.UUID, obj_in: BrokerAccountCreate) -> BrokerAccount:
    db_obj = BrokerAccount(
        user_id=user_id,
        broker=obj_in.broker,
        broker_client_id=obj_in.broker_client_id,
        access_token=obj_in.access_token,
        refresh_token=obj_in.refresh_token,
        token_expiry=obj_in.token_expiry,
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def get_user_broker_accounts(db: AsyncSession, user_id: uuid.UUID) -> Sequence[BrokerAccount]:
    stmt = select(BrokerAccount).where(BrokerAccount.user_id == user_id).order_by(BrokerAccount.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


async def delete_broker_account(db: AsyncSession, account_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    stmt = select(BrokerAccount).where(BrokerAccount.id == account_id, BrokerAccount.user_id == user_id)
    result = await db.execute(stmt)
    db_obj = result.scalar_one_or_none()
    if not db_obj:
        return False
    await db.delete(db_obj)
    await db.commit()
    return True
