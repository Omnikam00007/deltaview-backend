import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.holding import Holding
    from app.models.trade import Trade


class Instrument(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "instruments"

    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    isin: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    exchange: Mapped[str | None] = mapped_column(String(10))   # NSE | BSE | NFO
    segment: Mapped[str | None] = mapped_column(String(20))    # equity | fno | mf | etf | gold
    sector: Mapped[str | None] = mapped_column(String(100), index=True)
    lot_size: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relationships
    holdings: Mapped[list["Holding"]] = relationship(back_populates="instrument")
    trades: Mapped[list["Trade"]] = relationship(back_populates="instrument")
