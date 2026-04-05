import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.broker_account import BrokerAccount
    from app.models.instrument import Instrument


class Holding(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint("user_id", "broker_account_id", "instrument_id", name="uq_holdings_user_broker_instrument"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    broker_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("instruments.id"), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    avg_cost: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    ltp: Mapped[float | None] = mapped_column(Numeric(18, 4))
    current_value: Mapped[float | None] = mapped_column(Numeric(18, 2))
    pnl: Mapped[float | None] = mapped_column(Numeric(18, 2))
    pnl_percent: Mapped[float | None] = mapped_column(Numeric(10, 4))
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="holdings")
    broker_account: Mapped["BrokerAccount"] = relationship(back_populates="holdings")
    instrument: Mapped["Instrument"] = relationship(back_populates="holdings")
