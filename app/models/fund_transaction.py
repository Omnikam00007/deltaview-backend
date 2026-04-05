import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPrimaryKey


class FundTransaction(UUIDPrimaryKey, Base):
    __tablename__ = "fund_transactions"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    broker_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id"), nullable=False)
    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("bank_accounts.id"))
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)  # add | withdraw
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    payment_method: Mapped[str | None] = mapped_column(String(20))   # upi | netbanking | neft
    speed: Mapped[str | None] = mapped_column(String(20))             # instant | normal
    status: Mapped[str] = mapped_column(String(20), default="initiated", nullable=False)  # initiated|processing|success|failed
    transaction_ref: Mapped[str | None] = mapped_column(String(100))
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
