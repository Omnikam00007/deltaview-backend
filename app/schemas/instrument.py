import uuid
from pydantic import BaseModel, ConfigDict


class InstrumentCreate(BaseModel):
    symbol: str
    isin: str | None = None
    name: str | None = None
    exchange: str | None = None
    segment: str | None = None
    sector: str | None = None
    lot_size: int = 1


class InstrumentUpdate(BaseModel):
    symbol: str | None = None
    name: str | None = None
    exchange: str | None = None
    segment: str | None = None
    sector: str | None = None
    lot_size: int | None = None


class InstrumentResponse(BaseModel):
    id: uuid.UUID
    symbol: str
    isin: str | None
    name: str | None
    exchange: str | None
    segment: str | None
    sector: str | None
    lot_size: int

    model_config = ConfigDict(from_attributes=True)
