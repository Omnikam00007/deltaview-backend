import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDPrimaryKey

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.broker_account import BrokerAccount


class LedgerEntry(UUIDPrimaryKey, Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        Index("ix_ledger_user_date", "user_id", "entry_date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    broker_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id"), nullable=False, index=True)
    entry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    narration: Mapped[str | None] = mapped_column(Text)                 # human-readable (generated)
    original_narration: Mapped[str | None] = mapped_column(Text)        # raw from broker
    entry_type: Mapped[str] = mapped_column(String(10), nullable=False)  # credit | debit
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    closing_balance: Mapped[float | None] = mapped_column(Numeric(18, 2))
    category: Mapped[str | None] = mapped_column(String(50), index=True)  # deposit|withdrawal|charge|dividend|interest|other
    help_text: Mapped[str | None] = mapped_column(Text)
    transaction_ref: Mapped[str | None] = mapped_column(String(100))
    raw_data: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    broker_account: Mapped["BrokerAccount"] = relationship()
