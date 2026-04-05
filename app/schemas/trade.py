import uuid
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict

from app.schemas.holding import InstrumentBrief, BrokerAccountBrief


class TradeCreate(BaseModel):
    broker_account_id: uuid.UUID
    instrument_id: uuid.UUID
    trade_type: str  # BUY | SELL
    quantity: float
    price: float
    trade_value: float
    trade_date: date
    settlement_date: date | None = None
    order_id: str | None = None
    segment: str = "equity"
    charges: dict = {}
    raw_data: dict | None = None


class TradeResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    broker_account_id: uuid.UUID
    instrument_id: uuid.UUID
    trade_type: str
    quantity: float
    price: float
    trade_value: float
    trade_date: date
    settlement_date: date | None
    order_id: str | None
    segment: str
    charges: dict
    raw_data: dict | None
    created_at: datetime

    instrument: InstrumentBrief | None = None
    broker_account: BrokerAccountBrief | None = None

    model_config = ConfigDict(from_attributes=True)
