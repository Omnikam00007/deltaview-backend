import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPrimaryKey


class FundsBalance(UUIDPrimaryKey, Base):
    __tablename__ = "funds_balances"
    __table_args__ = (
        UniqueConstraint("user_id", "broker_account_id", name="uq_funds_balances_user_broker"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    broker_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id", ondelete="CASCADE"), nullable=False)
    available_margin: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    withdrawable_balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    unsettled_credits: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    pledged_margin: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    used_margin: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    total_margin: Mapped[float] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
