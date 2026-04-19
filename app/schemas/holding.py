import uuid
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict

# --------------- Holdings ---------------

class HoldingCreate(BaseModel):
    broker_account_id: uuid.UUID
    instrument_id: uuid.UUID
    quantity: float
    avg_cost: float
    ltp: float | None = None
    current_value: float | None = None
    pnl: float | None = None
    pnl_percent: float | None = None
    as_of_date: date

class HoldingUpdate(BaseModel):
    quantity: float | None = None
    avg_cost: float | None = None
    ltp: float | None = None
    current_value: float | None = None
    pnl: float | None = None
    pnl_percent: float | None = None
    as_of_date: date | None = None

class InstrumentBrief(BaseModel):
    """Minimal instrument info embedded in holding responses."""
    id: uuid.UUID
    symbol: str
    name: str | None
    exchange: str | None
    segment: str | None
    sector: str | None

    model_config = ConfigDict(from_attributes=True)

class BrokerAccountBrief(BaseModel):
    """Minimal broker account info embedded in holding responses."""
    id: uuid.UUID
    broker: str
    broker_client_id: str | None

    model_config = ConfigDict(from_attributes=True)

class HoldingResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    broker_account_id: uuid.UUID
    instrument_id: uuid.UUID
    quantity: float
    avg_cost: float
    ltp: float | None
    current_value: float | None
    pnl: float | None
    pnl_percent: float | None
    as_of_date: date
    created_at: datetime
    updated_at: datetime

    # Nested relations (populated when eager-loaded)
    instrument: InstrumentBrief | None = None
    broker_account: BrokerAccountBrief | None = None

    model_config = ConfigDict(from_attributes=True)


class ConsolidatedHoldingResponse(BaseModel):
    """A single stock row aggregated across all broker accounts."""
    id: str
    user_id: str
    instrument_id: str
    quantity: float
    avg_cost: float
    ltp: float | None = None
    current_value: float | None = None
    pnl: float | None = None
    pnl_percent: float | None = None
    as_of_date: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    instrument: InstrumentBrief | None = None
    brokers: list[BrokerAccountBrief] = []



# --------------- Holding Tags ---------------

class HoldingTagCreate(BaseModel):
    instrument_id: uuid.UUID
    tag_name: str


class HoldingTagResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    instrument_id: uuid.UUID
    tag_name: str
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# --------------- Portfolio Summary ---------------

class PortfolioSummary(BaseModel):
    total_invested: float
    current_value: float
    total_pnl: float
    total_pnl_percent: float
    holding_count: int
