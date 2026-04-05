import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class BrokerAccountCreate(BaseModel):
    broker: str
    broker_client_id: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_expiry: datetime | None = None


class BrokerAccountUpdate(BaseModel):
    is_active: bool | None = None
    sync_status: str | None = None
    last_synced_at: datetime | None = None


class BrokerAccountResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    broker: str
    broker_client_id: str | None
    is_active: bool
    last_synced_at: datetime | None
    sync_status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
