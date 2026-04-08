"""Debt snapshot builder -- persists monthly principal snapshots."""
from __future__ import annotations

from datetime import date
from typing import Iterable

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from finance_app.domain.debts.repository import fetch_snapshot, save_snapshot
from finance_app.domain.debts.service import get_debts_principal
from finance_app.models import DebtSnapshotMonthly


def _month_start(day: date) -> date:
    """Normalize a date to the first of its month."""
    return day.replace(day=1)


def _iter_months(start_month: date, end_month: date) -> Iterable[date]:
    """Yield first-of-month dates from *start_month* through *end_month*."""
    current = _month_start(start_month)
    end_month = _month_start(end_month)
    while current <= end_month:
        yield current
        current = current + relativedelta(months=1)


def build_debt_snapshots(
    db: Session,
    start_month: date,
    end_month: date,
    rebuild: bool = False,
) -> None:
    """Create or refresh monthly principal snapshots for all open debts.

    Args:
        db: Database session.
        start_month: First month to snapshot (inclusive).
        end_month: Last month to snapshot (inclusive).
        rebuild: If True, replace existing snapshots instead of skipping.
    """
    for month_start in _iter_months(start_month, end_month):
        records = get_debts_principal(db, month_start)
        for record in records:
            if record.status != "open":
                continue
            existing = fetch_snapshot(db, record.debt_id, month_start)
            if existing and not rebuild:
                continue
            if existing and rebuild:
                db.delete(existing)
                db.flush()

            snapshot = DebtSnapshotMonthly(
                debt_id=record.debt_id,
                snapshot_month=month_start.strftime("%Y-%m"),
                as_of_date=month_start,
                currency_code=record.currency_code,
                principal_original=float(record.principal_original),
                principal_cop=float(record.principal_cop),
            )
            save_snapshot(db, snapshot)
        db.commit()
