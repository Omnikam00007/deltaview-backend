import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.broker_account import BrokerAccount
    from app.models.instrument import Instrument
    from app.models.trade import Trade


class RealizedPnl(UUIDPrimaryKey, Base):
    __tablename__ = "realized_pnl"
    __table_args__ = (
        Index("ix_rpnl_user_sell", "user_id", "sell_date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    broker_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id"), nullable=False)
    instrument_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("instruments.id"), nullable=False)
    buy_trade_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("trades.id"))
    sell_trade_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("trades.id"))
    quantity: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    buy_value: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    sell_value: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    gross_pnl: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    charges: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    net_pnl: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    buy_date: Mapped[date] = mapped_column(Date, nullable=False)
    sell_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    holding_period_days: Mapped[int | None] = mapped_column(Integer)
    tax_category: Mapped[str | None] = mapped_column(String(10))   # STCG | LTCG
    financial_year: Mapped[str | None] = mapped_column(String(10))  # 2025-26
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user: Mapped["User"] = relationship()
    instrument: Mapped["Instrument"] = relationship()
    buy_trade: Mapped["Trade | None"] = relationship(foreign_keys=[buy_trade_id])
    sell_trade: Mapped["Trade | None"] = relationship(foreign_keys=[sell_trade_id])
