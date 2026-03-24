"""
Shared helpers for report endpoints.
"""
import logging
from typing import Optional, Tuple
from datetime import date
from dateutil.relativedelta import relativedelta

from sqlalchemy.orm import Session, joinedload

from finance_app.models import Transaction, ExchangeRate
from finance_app.services.budget_service import build_spent_transactions_query

logger = logging.getLogger(__name__)


def get_exchange_rate(db: Session) -> float:
    """Get current USD to COP exchange rate."""
    rate = db.query(ExchangeRate).order_by(ExchangeRate.date.desc()).first()
    return rate.rate if rate else 4000.0


def parse_date_range(start_date: Optional[str], end_date: Optional[str]) -> Tuple[date, date]:
    """Parse ISO date strings, defaulting to current month."""
    today = date.today()
    if not start_date:
        start_date = today.replace(day=1).isoformat()
    if not end_date:
        end_date = today.isoformat()
    return date.fromisoformat(start_date), date.fromisoformat(end_date)


def convert_to_currency(amount: float, from_currency_id: int, to_currency_id: int, exchange_rate: float) -> float:
    """Convert amount from one currency to another.

    Args:
        amount: Amount to convert
        from_currency_id: Source currency ID (1=COP, 2=USD)
        to_currency_id: Target currency ID (1=COP, 2=USD)
        exchange_rate: USD to COP exchange rate
    """
    if from_currency_id == to_currency_id:
        return amount
    if from_currency_id == 2 and to_currency_id == 1:
        return amount * exchange_rate
    if from_currency_id == 1 and to_currency_id == 2:
        if exchange_rate <= 0:
            return amount
        return amount / exchange_rate
    return amount


def expense_allocations(db: Session, start_date_obj: date, end_date_exclusive: date):
    """Return (transaction, category, abs_amount) tuples for expenses in range.

    When a transaction has splits, verifies that split amounts sum to the
    transaction total.  If there is a discrepancy, the split amounts are
    scaled proportionally so the full transaction amount is allocated.
    """
    transactions = build_spent_transactions_query(db, start_date_obj, end_date_exclusive).options(
        joinedload(Transaction.splits),
        joinedload(Transaction.category),
    ).all()

    allocations = []
    for tx in transactions:
        if tx.splits:
            split_total = sum(abs(s.amount) for s in tx.splits)
            tx_total = abs(tx.amount)
            if split_total > 0 and abs(split_total - tx_total) > 0.01:
                logger.warning(
                    "Transaction %s: splits sum %.2f != tx amount %.2f — scaling splits",
                    tx.id, split_total, tx_total,
                )
                scale = tx_total / split_total
                for split in tx.splits:
                    allocations.append((tx, split.category, abs(split.amount) * scale))
            else:
                for split in tx.splits:
                    allocations.append((tx, split.category, abs(split.amount)))
        else:
            allocations.append((tx, tx.category, abs(tx.amount)))
    return allocations
