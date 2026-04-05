from pydantic import BaseModel


class MarketIndexResponse(BaseModel):
    symbol: str
    name: str
    value: float
    change: float
    change_percent: float

    model_config = {"from_attributes": True}
