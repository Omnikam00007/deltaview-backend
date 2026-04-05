from fastapi import APIRouter

from app.api.v1.endpoints import (
    health, auth, bank_accounts, broker_accounts, fund_transactions,
    holdings, trades, instruments, ledger_entries, funds_balance, analytics,
    market,
)

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(bank_accounts.router, prefix="/bank-accounts", tags=["Bank Accounts"])
api_router.include_router(broker_accounts.router, prefix="/broker-accounts", tags=["Broker Accounts"])
api_router.include_router(fund_transactions.router, prefix="/fund-transactions", tags=["Fund Transactions"])
api_router.include_router(holdings.router, prefix="/holdings", tags=["Holdings"])
api_router.include_router(trades.router, prefix="/trades", tags=["Trades"])
api_router.include_router(instruments.router, prefix="/instruments", tags=["Instruments"])
api_router.include_router(ledger_entries.router, prefix="/ledger-entries", tags=["Ledger Entries"])
api_router.include_router(funds_balance.router, prefix="/funds-balance", tags=["Funds Balance"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(market.router, prefix="/market", tags=["Market"])

