import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class FundTransactionCreate(BaseModel):
    broker_account_id: uuid.UUID
    bank_account_id: uuid.UUID | None = None
    transaction_type: str  # 'add' or 'withdraw'
    amount: float
    payment_method: str | None = None
    speed: str | None = None


class FundTransactionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    broker_account_id: uuid.UUID
    bank_account_id: uuid.UUID | None
    transaction_type: str
    amount: float
    payment_method: str | None
    speed: str | None
    status: str
    transaction_ref: str | None
    initiated_at: datetime
    completed_at: datetime | None
    failure_reason: str | None

    model_config = ConfigDict(from_attributes=True)
