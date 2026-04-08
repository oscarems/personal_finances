from datetime import date
from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from finance_app.models import Account, Transaction, ReconciliationSession
from finance_app.services.transaction_service import create_adjustment


def get_reconciliation_summary(
    db: Session,
    account_id: int,
    statement_date: date | None = None
) -> dict:
    """Get cleared vs uncleared balances for an account.

    Args:
        db: Database session.
        account_id: Account to reconcile.
        statement_date: Optional cutoff date for transactions.

    Returns:
        Dict with cleared_balance, uncleared_balance, current_balance.

    Raises:
        ValueError: If account not found.
    """
    account = db.query(Account).get(account_id)
    if not account:
        raise ValueError("Account not found")

    base_query = db.query(Transaction).filter(Transaction.account_id == account_id)
    if statement_date:
        base_query = base_query.filter(Transaction.date <= statement_date)

    cleared_balance = base_query.filter(Transaction.cleared == True).with_entities(
        func.coalesce(func.sum(Transaction.amount), 0.0)
    ).scalar()

    uncleared_balance = base_query.filter(Transaction.cleared == False).with_entities(
        func.coalesce(func.sum(Transaction.amount), 0.0)
    ).scalar()

    return {
        "account_id": account.id,
        "account_name": account.name,
        "statement_date": statement_date.isoformat() if statement_date else None,
        "cleared_balance": cleared_balance or 0.0,
        "uncleared_balance": uncleared_balance or 0.0,
        "current_balance": account.balance
    }


def mark_transactions_cleared(
    db: Session,
    transaction_ids: list[int],
    cleared: bool
) -> int:
    """Bulk update the cleared status of transactions.

    Args:
        db: Database session.
        transaction_ids: IDs to update.
        cleared: New cleared status.

    Returns:
        Number of rows updated.
    """
    if not transaction_ids:
        return 0

    updated = db.query(Transaction).filter(
        Transaction.id.in_(transaction_ids)
    ).update({Transaction.cleared: cleared}, synchronize_session=False)
    db.commit()
    return updated


def create_reconciliation_session(
    db: Session,
    account_id: int,
    statement_date: date,
    statement_balance: float,
    notes: str | None = None,
    create_adjustment_entry: bool = False
) -> ReconciliationSession:
    """Create a reconciliation session and optionally an adjustment transaction.

    Args:
        db: Database session.
        account_id: Account being reconciled.
        statement_date: Bank statement date.
        statement_balance: Real balance from bank statement.
        notes: Optional notes for the session.
        create_adjustment_entry: If True, create an adjustment transaction for the difference.

    Returns:
        The created ReconciliationSession.
    """
    summary = get_reconciliation_summary(db, account_id, statement_date)
    cleared_balance = summary["cleared_balance"]
    difference = statement_balance - cleared_balance

    adjustment_id = None
    if create_adjustment_entry:
        adjustment = create_adjustment(
            db,
            {
                "account_id": account_id,
                "date": statement_date,
                "actual_balance": statement_balance,
                "memo": notes or "Reconciliation adjustment"
            }
        )
        adjustment_id = adjustment.id

    session = ReconciliationSession(
        account_id=account_id,
        statement_date=statement_date,
        statement_balance=statement_balance,
        cleared_balance=cleared_balance,
        difference=difference,
        notes=notes,
        adjustment_transaction_id=adjustment_id
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session
