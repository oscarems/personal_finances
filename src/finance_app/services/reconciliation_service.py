from datetime import date
from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from finance_app.models import Account, Transaction, ReconciliationSession
from finance_app.services.transaction_service import create_adjustment


def get_reconciliation_summary(
    db: Session,
    account_id: int,
    statement_date: Optional[date] = None
) -> dict:
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
    transaction_ids: List[int],
    cleared: bool
) -> int:
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
    notes: Optional[str] = None,
    create_adjustment_entry: bool = False
) -> ReconciliationSession:
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
