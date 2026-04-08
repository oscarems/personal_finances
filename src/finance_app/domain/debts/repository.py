"""Repository layer for debt data access."""
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
    """Fetch all debts, optionally filtering to active only.

    Args:
        db: Database session.
        include_inactive: If False, only return active debts.

    Returns:
        List of Debt model instances.
    """
    query = db.query(Debt)
    if not include_inactive:
        query = query.filter(Debt.is_active == True)
    return query.all()


def fetch_recurring_expense_transactions(db: Session) -> List[RecurringTransaction]:
    """Fetch all active recurring transactions.

    Args:
        db: Database session.

    Returns:
        List of active RecurringTransaction instances.
    """
    return (
        db.query(RecurringTransaction)
        .filter(RecurringTransaction.is_active == True)
        .all()
    )


def fetch_currency_codes(db: Session) -> Dict[int, str]:
    """Build a mapping of currency ID to currency code.

    Args:
        db: Database session.

    Returns:
        Dict mapping currency IDs to their string codes (e.g. ``{1: 'COP', 2: 'USD'}``).
    """
    return {currency.id: currency.code for currency in db.query(Currency).all()}


def fetch_debt_category_allocations(db: Session) -> Dict[int, List[int]]:
    """Build a mapping of category_id to list of debt_ids for allocation routing.

    Args:
        db: Database session.

    Returns:
        Dict mapping category IDs to lists of debt IDs allocated to them.
    """
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
) -> DebtSnapshotMonthly | DebtSnapshotProjectedMonthly | None:
    """Fetch a debt snapshot for a specific month.

    Args:
        db: Database session.
        debt_id: ID of the debt.
        as_of_date: Month start date to look up.
        projected: If True, use the projected snapshot table.

    Returns:
        Snapshot record or None if not found.
    """
    model = DebtSnapshotProjectedMonthly if projected else DebtSnapshotMonthly
    return (
        db.query(model)
        .filter(model.debt_id == debt_id, model.as_of_date == as_of_date)
        .first()
    )


def save_snapshot(db: Session, snapshot: DebtSnapshotMonthly | DebtSnapshotProjectedMonthly) -> None:
    """Add a snapshot to the session (caller must commit).

    Args:
        db: Database session.
        snapshot: Snapshot model instance to persist.
    """
    db.add(snapshot)
