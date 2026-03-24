from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from finance_app.models import Debt
from finance_app.services.debt.amortization_engine import AmortizationEngine


def calculate_scheduled_principal_balance(debt: Debt, as_of_date: date) -> float:
    engine = AmortizationEngine(db=None)
    return engine.balance_as_of(debt, as_of_date, mode="plan")


def calculate_debt_balance_as_of(
    db: Session,
    debt: Debt,
    as_of_date: date,
    today: date | None = None,
    include_projection: bool = False,
) -> float:
    if debt.debt_type == "credit_card":
        return debt.current_balance or 0.0

    mode = "hybrid" if include_projection else "actual"
    engine = AmortizationEngine(db=db)
    return engine.balance_as_of(debt, as_of_date, mode=mode)


def calculate_mortgage_principal_balance(
    db: Session,
    debt: Debt,
    as_of_date: date | None = None,
) -> float:
    target = as_of_date or date.today()
    engine = AmortizationEngine(db=db)
    return engine.balance_as_of(debt, target, mode="hybrid")


def refresh_mortgage_current_balance(
    db: Session,
    debt: Debt,
    as_of_date: date | None = None,
) -> float:
    balance = calculate_mortgage_principal_balance(db, debt, as_of_date=as_of_date)
    debt.current_balance = balance
    if debt.debt_type == "mortgage":
        debt.principal_balance = Decimal(str(balance))
    return balance


def build_debt_balance_map(
    db: Session,
    debt: Debt,
    end_month: date,
    today: date | None = None,
) -> Dict[date, float]:
    if debt.debt_type == "credit_card":
        return {end_month: debt.current_balance or 0.0}

    engine = AmortizationEngine(db=db)
    schedule = engine.generate_schedule(debt, as_of=end_month, mode="hybrid")
    return {
        row["date"] + relativedelta(months=1, days=-1): row["ending_balance"]
        for row in schedule
        if row["date"] <= end_month.replace(day=1)
    }
