from __future__ import annotations

from datetime import date
from typing import Dict, Optional, Tuple

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from finance_app.models import Debt, DebtAmortizationMonthly
from finance_app.services.debt.amortization_engine import AmortizationEngine, UnsupportedAmortizationTypeError


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _iter_months(start_month: date, end_month: date):
    current = _month_start(start_month)
    while current <= _month_start(end_month):
        yield current
        current += relativedelta(months=1)


def ensure_debt_amortization_records(
    db: Session,
    start_month: date,
    end_month: date,
    months_ahead: int = 12,
    today: Optional[date] = None,
) -> None:
    today = today or date.today()
    current_month = _month_start(today)
    projection_end = current_month + relativedelta(months=months_ahead)
    end_month = max(_month_start(end_month), projection_end)
    start_month = _month_start(start_month)

    debts = db.query(Debt).filter(Debt.is_active == True).all()
    engine = AmortizationEngine(db=db)

    for debt in debts:
        if debt.debt_type == "credit_card":
            continue

        try:
            schedule = engine.generate_schedule(debt, as_of=end_month, mode="hybrid")
        except UnsupportedAmortizationTypeError:
            continue

        existing = db.query(DebtAmortizationMonthly).filter(
            DebtAmortizationMonthly.debt_id == debt.id,
            DebtAmortizationMonthly.as_of_date >= start_month,
            DebtAmortizationMonthly.as_of_date <= end_month,
        ).all()
        existing_by_date = {entry.as_of_date: entry for entry in existing}
        schedule_by_month = {row["date"]: row for row in schedule}

        for month_start in _iter_months(start_month, end_month):
            row = schedule_by_month.get(month_start)
            if not row:
                continue
            status = "pagado" if row["is_paid_real"] else "proyeccion"
            interest_rate_calc = (row["interest"] / row["opening_balance"] * 100) if row["opening_balance"] else 0.0

            existing_entry = existing_by_date.get(month_start)
            if existing_entry:
                # Update existing record if the balance has changed
                if abs(float(existing_entry.principal_remaining) - row["ending_balance"]) > 0.01:
                    existing_entry.principal_payment = row["principal"]
                    existing_entry.interest_payment = row["interest"]
                    existing_entry.total_payment = row["payment"]
                    existing_entry.principal_remaining = row["ending_balance"]
                    existing_entry.interest_rate_calculated = interest_rate_calc
                    existing_entry.status = status
                continue

            db.add(
                DebtAmortizationMonthly(
                    debt_id=debt.id,
                    snapshot_month=month_start.strftime("%Y-%m"),
                    as_of_date=month_start,
                    currency_code=debt.currency_code,
                    principal_payment=row["principal"],
                    interest_payment=row["interest"],
                    total_payment=row["payment"],
                    principal_remaining=row["ending_balance"],
                    interest_rate_calculated=interest_rate_calc,
                    status=status,
                )
            )
    db.commit()


def fetch_amortization_for_month(
    db: Session,
    target_month: date,
    debt_ids: Optional[list[int]] = None,
) -> Dict[int, DebtAmortizationMonthly]:
    target_month = _month_start(target_month)
    query = db.query(DebtAmortizationMonthly).filter(
        DebtAmortizationMonthly.as_of_date == target_month
    )
    if debt_ids:
        query = query.filter(DebtAmortizationMonthly.debt_id.in_(debt_ids))
    return {entry.debt_id: entry for entry in query.all()}


def fetch_amortization_range(
    db: Session,
    start_month: date,
    end_month: date,
    debt_ids: Optional[list[int]] = None,
) -> Dict[Tuple[int, date], DebtAmortizationMonthly]:
    query = db.query(DebtAmortizationMonthly).filter(
        DebtAmortizationMonthly.as_of_date >= _month_start(start_month),
        DebtAmortizationMonthly.as_of_date <= _month_start(end_month),
    )
    if debt_ids:
        query = query.filter(DebtAmortizationMonthly.debt_id.in_(debt_ids))
    return {(entry.debt_id, entry.as_of_date): entry for entry in query.all()}
