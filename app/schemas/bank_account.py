import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class BankAccountCreate(BaseModel):
    bank_name: str
    account_number: str
    ifsc_code: str | None = None
    is_primary: bool = False


class BankAccountUpdate(BaseModel):
    bank_name: str | None = None
    account_number: str | None = None
    ifsc_code: str | None = None
    is_primary: bool | None = None


class BankAccountResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    bank_name: str
    account_number: str
    ifsc_code: str | None = None
    is_primary: bool
    is_verified: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
