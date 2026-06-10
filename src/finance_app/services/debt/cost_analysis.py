"""
Debt cost analysis — historical payment breakdown and minimum-payment projection.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from finance_app.models import Debt, DebtPayment
from finance_app.services.debt.helpers import (
    calculate_suggested_minimum_payment,
    payment_principal_amount,
)


def analyze_debt_cost(db: Session, debt: Debt) -> dict:
    """Return a cost breakdown for a debt: historical payments and minimum-payment projection.

    Args:
        db: Active SQLAlchemy session.
        debt: Debt model instance to analyse.

    Returns:
        A dict with keys:
          - ``interest_paid_to_date`` – sum of interest from all DebtPayment records.
          - ``principal_paid_to_date`` – sum of principal (derived when not explicit).
          - ``total_paid_to_date`` – sum of payment amounts.
          - ``interest_pct_of_paid`` – interest as a percentage of total paid (0 when no payments).
          - ``minimum_projection`` – sub-dict with month count, interest totals, and payoff date
            when paying only the suggested minimum each month.
    """
    # --- Historical payments ---
    payments = db.query(DebtPayment).filter_by(debt_id=debt.id).all()

    interest_paid = sum(float(p.interest or 0.0) for p in payments)
    principal_paid = sum(payment_principal_amount(p) for p in payments)
    total_paid = sum(float(p.amount or 0.0) for p in payments)
    interest_pct = (interest_paid / total_paid * 100) if total_paid > 0 else 0.0

    # --- Minimum-payment projection ---
    minimum_projection = _project_minimum_payment(debt)

    return {
        "interest_paid_to_date": round(interest_paid, 2),
        "principal_paid_to_date": round(principal_paid, 2),
        "total_paid_to_date": round(total_paid, 2),
        "interest_pct_of_paid": round(interest_pct, 2),
        "minimum_projection": minimum_projection,
    }


def _monthly_rate_from_debt(debt: Debt) -> Optional[float]:
    """Derive the effective monthly interest rate from the debt's annual rate fields."""
    annual_raw = debt.annual_interest_rate or debt.interest_rate
    if not annual_raw:
        return None
    annual = float(annual_raw)
    annual_decimal = annual / 100 if annual > 1 else annual
    return (1 + annual_decimal) ** (1 / 12) - 1


def _project_minimum_payment(debt: Debt) -> dict:
    """Simulate paying only the suggested minimum each month until the balance reaches zero.

    Args:
        debt: Debt model instance.

    Returns:
        Dict with projection keys; values are ``None`` when the projection cannot be computed.
    """
    monthly_minimum = calculate_suggested_minimum_payment(debt)
    balance = float(debt.current_balance or 0.0)

    empty: dict = {
        "monthly_minimum": monthly_minimum,
        "months_if_minimum": None,
        "total_interest_if_minimum": None,
        "total_paid_if_minimum": None,
        "payoff_date_minimum": None,
    }

    monthly_rate = _monthly_rate_from_debt(debt)
    if monthly_rate is None or monthly_minimum <= 0 or balance <= 0:
        return empty

    MAX_MONTHS = 600
    total_interest = 0.0
    total_paid_sim = 0.0
    months = 0

    today = date.today()

    for _ in range(MAX_MONTHS):
        if balance <= 0:
            break
        interest = balance * monthly_rate
        payment = min(monthly_minimum, balance + interest)
        balance = balance + interest - payment
        total_interest += interest
        total_paid_sim += payment
        months += 1
        if balance <= 0.01:
            balance = 0.0
            break
    else:
        # Did not converge within the limit
        return empty

    # Payoff date: advance 'months' months from the start of next month
    payoff_date = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    for _ in range(months - 1):
        payoff_date = (payoff_date + timedelta(days=32)).replace(day=1)

    return {
        "monthly_minimum": round(monthly_minimum, 2),
        "months_if_minimum": months,
        "total_interest_if_minimum": round(total_interest, 2),
        "total_paid_if_minimum": round(total_paid_sim, 2),
        "payoff_date_minimum": payoff_date.isoformat(),
    }
