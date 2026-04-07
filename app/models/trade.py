import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, func, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.broker_account import BrokerAccount
    from app.models.instrument import Instrument


class Trade(UUIDPrimaryKey, Base):
    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_user_date", "user_id", "trade_date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    broker_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id"), nullable=False)
    instrument_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("instruments.id"), nullable=False, index=True)
    trade_type: Mapped[str] = mapped_column(String(10), nullable=False)      # BUY | SELL
    quantity: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    trade_value: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    settlement_date: Mapped[date | None] = mapped_column(Date)
    order_id: Mapped[str | None] = mapped_column(String(100))
    segment: Mapped[str] = mapped_column(String(20), default="equity", nullable=False)
    charges: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # { brokerage, stt, gst, stamp_duty }
    raw_data: Mapped[dict | None] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="trades")
    broker_account: Mapped["BrokerAccount"] = relationship(back_populates="trades")
    instrument: Mapped["Instrument"] = relationship(back_populates="trades")
