import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.holding import Holding
    from app.models.trade import Trade


class BrokerAccount(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "broker_accounts"
    __table_args__ = (UniqueConstraint("user_id", "broker", "broker_client_id", name="uq_broker_accounts_user_broker_client"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    broker: Mapped[str] = mapped_column(String(50), nullable=False)          # zerodha | groww | upstox
    broker_client_id: Mapped[str | None] = mapped_column(String(100))
    access_token: Mapped[str | None] = mapped_column(String)                 # encrypted
    refresh_token: Mapped[str | None] = mapped_column(String)                # encrypted
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)  # pending|syncing|success|failed

    # Relationships
    user: Mapped["User"] = relationship(back_populates="broker_accounts")
    holdings: Mapped[list["Holding"]] = relationship(back_populates="broker_account", cascade="all, delete-orphan")
    trades: Mapped[list["Trade"]] = relationship(back_populates="broker_account", cascade="all, delete-orphan")
