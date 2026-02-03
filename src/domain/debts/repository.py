from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from finance_app.models import (
    Currency,
    Debt,
    DebtCategoryAllocation,
    DebtSnapshotMonthly,
    DebtSnapshotProjectedMonthly,
    RecurringTransaction,
)


def fetch_debts(db: Session, include_inactive: bool = True) -> List[Debt]:
    query = db.query(Debt)
    if not include_inactive:
        query = query.filter(Debt.is_active == True)
    return query.all()


def fetch_recurring_expense_transactions(db: Session) -> List[RecurringTransaction]:
    return (
        db.query(RecurringTransaction)
        .filter(RecurringTransaction.is_active == True)
        .all()
    )


def fetch_currency_codes(db: Session) -> Dict[int, str]:
    return {currency.id: currency.code for currency in db.query(Currency).all()}


def fetch_debt_category_allocations(db: Session) -> Dict[int, List[int]]:
    allocations = db.query(DebtCategoryAllocation).all()
    mapping: Dict[int, List[int]] = {}
    for allocation in allocations:
        mapping.setdefault(allocation.category_id, []).append(allocation.debt_id)
    return mapping


def fetch_snapshot(
    db: Session,
    debt_id: int,
    as_of_date: date,
    projected: bool = False,
) -> Optional[DebtSnapshotMonthly | DebtSnapshotProjectedMonthly]:
    model = DebtSnapshotProjectedMonthly if projected else DebtSnapshotMonthly
    return (
        db.query(model)
        .filter(model.debt_id == debt_id, model.as_of_date == as_of_date)
        .first()
    )


def save_snapshot(db: Session, snapshot: DebtSnapshotMonthly | DebtSnapshotProjectedMonthly) -> None:
    db.add(snapshot)
