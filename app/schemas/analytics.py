import uuid
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict


# --------------- Ledger Entries ---------------

class LedgerEntryCreate(BaseModel):
    broker_account_id: uuid.UUID
    entry_date: datetime
    narration: str | None = None
    original_narration: str | None = None
    entry_type: str  # credit | debit
    amount: float
    closing_balance: float | None = None
    category: str | None = None
    help_text: str | None = None
    transaction_ref: str | None = None
    raw_data: dict | None = None


class LedgerEntryResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    broker_account_id: uuid.UUID
    entry_date: datetime
    narration: str | None
    original_narration: str | None
    entry_type: str
    amount: float
    closing_balance: float | None
    category: str | None
    help_text: str | None
    transaction_ref: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --------------- Funds Balance ---------------

class FundsBalanceUpsert(BaseModel):
    broker_account_id: uuid.UUID
    available_margin: float = 0
    withdrawable_balance: float = 0
    unsettled_credits: float = 0
    pledged_margin: float = 0
    used_margin: float = 0
    total_margin: float = 0


class FundsBalanceResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    broker_account_id: uuid.UUID
    available_margin: float
    withdrawable_balance: float
    unsettled_credits: float
    pledged_margin: float
    used_margin: float
    total_margin: float
    as_of: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --------------- Daily P&L ---------------

class DailyPnlCreate(BaseModel):
    trade_date: date
    pnl: float = 0
    trade_count: int = 0
    segment: str = "equity"


class DailyPnlResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    trade_date: date
    pnl: float
    trade_count: int
    segment: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --------------- Daily Portfolio Snapshot ---------------

class PortfolioSnapshotCreate(BaseModel):
    snapshot_date: date
    total_value: float
    total_invested: float | None = None
    total_pnl: float | None = None
    cash_balance: float | None = None


class PortfolioSnapshotResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    snapshot_date: date
    total_value: float
    total_invested: float | None
    total_pnl: float | None
    cash_balance: float | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --------------- Realized P&L ---------------

class RealizedPnlCreate(BaseModel):
    broker_account_id: uuid.UUID
    instrument_id: uuid.UUID
    buy_trade_id: uuid.UUID | None = None
    sell_trade_id: uuid.UUID | None = None
    quantity: float
    buy_value: float
    sell_value: float
    gross_pnl: float
    charges: dict = {}
    net_pnl: float
    buy_date: date
    sell_date: date
    holding_period_days: int | None = None
    tax_category: str | None = None
    financial_year: str | None = None


class RealizedPnlResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    broker_account_id: uuid.UUID
    instrument_id: uuid.UUID
    buy_trade_id: uuid.UUID | None
    sell_trade_id: uuid.UUID | None
    quantity: float
    buy_value: float
    sell_value: float
    gross_pnl: float
    charges: dict
    net_pnl: float
    buy_date: date
    sell_date: date
    holding_period_days: int | None
    tax_category: str | None
    financial_year: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --------------- Tax Summary ---------------

class TaxCategoryBreakdown(BaseModel):
    gains: float
    tax_rate: float
    exemption_limit: float
    taxable_amount: float
    tax: float

class TaxSummaryResponse(BaseModel):
    financial_year: str
    stcg: TaxCategoryBreakdown
    ltcg: TaxCategoryBreakdown
    total_gains: float
    total_tax_liability: float
