import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fund_transaction import FundTransaction
from app.models.funds_balance import FundsBalance
from app.models.ledger_entry import LedgerEntry
from app.schemas.fund_transaction import FundTransactionCreate


class InsufficientBalanceError(ValueError):
    """Raised when a withdrawal exceeds the withdrawable balance."""
    pass


async def create_fund_transaction(db: AsyncSession, user_id: uuid.UUID, obj_in: FundTransactionCreate) -> FundTransaction:
    """Create a fund transaction with row-level locking, balance validation,
    and settlement-aware balance updates.

    Raises:
        InsufficientBalanceError: if withdrawal amount > withdrawable_balance.
    """
    now = datetime.now(timezone.utc)

    # ── 1. Lock the FundsBalance row (SELECT ... FOR UPDATE) ──
    # This serializes concurrent deposits/withdrawals for the same broker account.
    stmt = (
        select(FundsBalance)
        .where(
            FundsBalance.user_id == user_id,
            FundsBalance.broker_account_id == obj_in.broker_account_id,
        )
        .with_for_update()  # Row-level lock — blocks until released
    )
    result = await db.execute(stmt)
    balance = result.scalar_one_or_none()

    if not balance:
        balance = FundsBalance(
            user_id=user_id,
            broker_account_id=obj_in.broker_account_id,
            available_margin=0,
            withdrawable_balance=0,
            unsettled_credits=0,
            pledged_margin=0,
            used_margin=0,
            total_margin=0,
        )
        db.add(balance)
        await db.flush()  # Ensure balance gets an ID before we read from it

    # ── 2. Validate withdrawal against real withdrawable balance ──
    if obj_in.transaction_type == "withdraw":
        if float(balance.withdrawable_balance) < obj_in.amount:
            raise InsufficientBalanceError(
                f"Insufficient withdrawable balance. "
                f"Available: ₹{float(balance.withdrawable_balance):,.2f}, "
                f"Requested: ₹{obj_in.amount:,.2f}"
            )

    # ── 3. Create the fund transaction record ──
    db_obj = FundTransaction(
        user_id=user_id,
        broker_account_id=obj_in.broker_account_id,
        bank_account_id=obj_in.bank_account_id,
        transaction_type=obj_in.transaction_type,
        amount=obj_in.amount,
        payment_method=obj_in.payment_method,
        speed=obj_in.speed,
        status="success",
        transaction_ref=f"DV-{uuid.uuid4().hex[:8].upper()}",
        completed_at=now,
    )
    db.add(db_obj)

    # ── 4. Update FundsBalance (settlement-aware) ──
    if obj_in.transaction_type == "add":
        # Deposits: available to trade, but NOT immediately withdrawable (T+2 settlement)
        balance.available_margin = float(balance.available_margin) + obj_in.amount
        balance.unsettled_credits = float(balance.unsettled_credits) + obj_in.amount
        # withdrawable_balance is NOT increased — funds settle after T+2
        # (A future Celery task should move unsettled → withdrawable after settlement)
    elif obj_in.transaction_type == "withdraw":
        balance.withdrawable_balance = float(balance.withdrawable_balance) - obj_in.amount
        balance.available_margin = float(balance.available_margin) - obj_in.amount

    # Recompute total_margin as sum of sub-fields
    balance.total_margin = (
        float(balance.available_margin)
        + float(balance.pledged_margin)
        + float(balance.used_margin)
    )
    balance.as_of = now

    # ── 5. Create a corresponding ledger entry ──
    ledger = LedgerEntry(
        user_id=user_id,
        broker_account_id=obj_in.broker_account_id,
        entry_date=now,  # DateTime, not Date — preserves intra-day ordering
        narration=f"Fund {'Deposit' if obj_in.transaction_type == 'add' else 'Withdrawal'} — ₹{obj_in.amount:,.2f}",
        original_narration=f"DeltaView {obj_in.transaction_type}",
        entry_type="credit" if obj_in.transaction_type == "add" else "debit",
        amount=obj_in.amount,
        closing_balance=float(balance.available_margin),
        category="funds_transfer",
        transaction_ref=db_obj.transaction_ref,
    )
    db.add(ledger)

    await db.flush()
    await db.refresh(db_obj)
    return db_obj


async def get_user_fund_transactions(db: AsyncSession, user_id: uuid.UUID) -> Sequence[FundTransaction]:
    stmt = (
        select(FundTransaction)
        .where(FundTransaction.user_id == user_id)
        .order_by(FundTransaction.initiated_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()
