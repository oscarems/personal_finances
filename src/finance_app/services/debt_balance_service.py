from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Tuple

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from finance_app.models import Debt, DebtPayment, MortgagePaymentAllocation
from finance_app.services.mortgage_service import calculate_monthly_payment


@dataclass(frozen=True)
class DebtPrincipalPayment:
    payment_date: date
    principal: float


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _month_end(day: date) -> date:
    return day.replace(day=1) + relativedelta(months=1) - relativedelta(days=1)


def _iter_months(start_month: date, end_month: date) -> Iterable[date]:
    current = start_month
    while current <= end_month:
        yield current
        current = current + relativedelta(months=1)


def _monthly_rate(annual_rate: float) -> float:
    if not annual_rate:
        return 0.0
    return (1 + annual_rate) ** (1 / 12) - 1


def _annual_rate_decimal(debt: Debt) -> float:
    if debt.annual_interest_rate is not None:
        try:
            rate = float(debt.annual_interest_rate)
        except (TypeError, ValueError):
            rate = 0.0
        return rate / 100 if rate > 1 else rate
    if debt.interest_rate:
        return debt.interest_rate / 100
    return 0.0


def _should_accrue_interest(debt: Debt) -> bool:
    return debt.debt_type != "mortgage"


def _payment_principal_from_debt_payment(payment: DebtPayment) -> float:
    if payment.principal is not None:
        return payment.principal
    if payment.amount is None:
        return 0.0
    interest = payment.interest or 0.0
    fees = payment.fees or 0.0
    return payment.amount - interest - fees


def _payment_principal_from_allocation(allocation: MortgagePaymentAllocation) -> float:
    principal = float(allocation.principal_paid or 0.0)
    principal += float(allocation.extra_principal_paid or 0.0)
    return principal


def _collect_principal_payments(db: Session, debt: Debt) -> List[DebtPrincipalPayment]:
    entries: List[DebtPrincipalPayment] = []

    allocations = db.query(MortgagePaymentAllocation).filter_by(loan_id=debt.id).all()
    allocation_transaction_ids = {
        allocation.transaction_id for allocation in allocations if allocation.transaction_id
    }

    for payment in db.query(DebtPayment).filter_by(debt_id=debt.id).all():
        if not payment.payment_date:
            continue
        if payment.transaction_id and payment.transaction_id in allocation_transaction_ids:
            continue
        principal = _payment_principal_from_debt_payment(payment)
        entries.append(DebtPrincipalPayment(payment.payment_date, principal))

    for allocation in allocations:
        if not allocation.payment_date:
            continue
        principal = _payment_principal_from_allocation(allocation)
        entries.append(DebtPrincipalPayment(allocation.payment_date, principal))

    return sorted(entries, key=lambda entry: entry.payment_date)


def _payments_by_month(
    payments: List[DebtPrincipalPayment],
) -> Dict[Tuple[int, int], List[DebtPrincipalPayment]]:
    by_month: Dict[Tuple[int, int], List[DebtPrincipalPayment]] = {}
    for entry in payments:
        key = (entry.payment_date.year, entry.payment_date.month)
        by_month.setdefault(key, []).append(entry)
    return by_month


def _calculate_months_between(start_date: date, end_date: date) -> int:
    return max(0, (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month))


def _payments_due_by_date(start_date: date, as_of_date: date) -> int:
    """
    Returns how many scheduled monthly payments should have occurred by as_of_date.
    Assumes the first payment is due on start_date and then every month.
    """
    if as_of_date < start_date:
        return 0
    months = (as_of_date.year - start_date.year) * 12 + (as_of_date.month - start_date.month)
    if as_of_date.day >= start_date.day:
        months += 1
    return max(0, months)


def _monthly_payment_from_terms(principal: float, annual_rate: float, term_months: int) -> float:
    if term_months <= 0:
        return 0.0
    if annual_rate == 0:
        return principal / term_months
    monthly_rate = _monthly_rate(annual_rate)
    numerator = monthly_rate * ((1 + monthly_rate) ** term_months)
    denominator = ((1 + monthly_rate) ** term_months) - 1
    if denominator == 0:
        return 0.0
    return principal * (numerator / denominator)


def calculate_scheduled_principal_balance(
    debt: Debt,
    as_of_date: date,
) -> float:
    """
    Calculate principal remaining based on start date, interest rate, term, and time elapsed.
    Uses fixed-payment amortization when monthly_payment is not provided.
    """
    if not debt.original_amount:
        return debt.current_balance or 0.0
    if not debt.start_date:
        return debt.current_balance or float(debt.original_amount)

    term_months = None
    if debt.loan_years:
        term_months = debt.loan_years * 12
    elif debt.term_months:
        term_months = int(debt.term_months)

    if not term_months:
        return debt.current_balance or float(debt.original_amount)

    annual_rate = _annual_rate_decimal(debt)
    monthly_rate = _monthly_rate(annual_rate)
    principal = float(debt.original_amount)
    payments_due = min(term_months, _payments_due_by_date(debt.start_date, as_of_date))

    monthly_payment = debt.monthly_payment
    if not monthly_payment or monthly_payment <= 0:
        # Prefer the mortgage calculator when terms are expressed in years.
        if debt.loan_years:
            monthly_payment = calculate_monthly_payment(principal, annual_rate, debt.loan_years)
        else:
            monthly_payment = _monthly_payment_from_terms(principal, annual_rate, term_months)

    if not monthly_payment or monthly_payment <= 0:
        return principal

    balance = principal
    for _ in range(payments_due):
        if balance <= 0:
            break
        interest = balance * monthly_rate if monthly_rate > 0 else 0.0
        principal_payment = max(0.0, monthly_payment - interest)
        if principal_payment > balance:
            principal_payment = balance
        balance = max(0.0, balance - principal_payment)

    return max(0.0, balance)


def calculate_debt_balance_as_of(
    db: Session,
    debt: Debt,
    as_of_date: date,
    today: date | None = None,
    include_projection: bool = False,
) -> float:
    if debt.debt_type == "mortgage":
        return calculate_mortgage_principal_balance(db, debt, as_of_date=as_of_date)

    if debt.debt_type == "credit_card":
        return debt.current_balance or 0.0

    if not debt.original_amount or not debt.start_date:
        return debt.current_balance or 0.0

    today = today or date.today()
    if as_of_date < debt.start_date:
        return 0.0

    accrue_interest = _should_accrue_interest(debt)
    annual_rate = _annual_rate_decimal(debt) if accrue_interest else 0.0
    monthly_rate = _monthly_rate(annual_rate) if accrue_interest else 0.0
    payments = _collect_principal_payments(db, debt)
    payments_by_month = _payments_by_month(payments)

    actual_end = min(as_of_date, today)
    start_month = _month_start(debt.start_date)
    end_month = _month_start(actual_end)
    balance = float(debt.original_amount)

    for month_start in _iter_months(start_month, end_month):
        month_end = _month_end(month_start)
        if month_end < debt.start_date:
            continue

        month_key = (month_start.year, month_start.month)

        if month_start < end_month or actual_end == month_end:
            if accrue_interest:
                balance += balance * monthly_rate
            principal_paid = sum(
                entry.principal for entry in payments_by_month.get(month_key, [])
            )
            balance = max(0.0, balance - principal_paid)
            continue

        principal_paid = sum(
            entry.principal
            for entry in payments_by_month.get(month_key, [])
            if entry.payment_date <= actual_end
        )
        balance = max(0.0, balance - principal_paid)

    if as_of_date <= today or not include_projection:
        return max(0.0, balance)

    current_month_end = _month_end(today)
    target_month_end = _month_end(as_of_date)
    months_ahead = _calculate_months_between(current_month_end, target_month_end)
    monthly_payment = debt.monthly_payment or 0.0

    for _ in range(months_ahead):
        if accrue_interest:
            interest = balance * monthly_rate
            balance += interest
            if monthly_payment > 0:
                principal_paid = max(0.0, monthly_payment - interest)
                balance = max(0.0, balance - principal_paid)
        else:
            if monthly_payment > 0:
                balance = max(0.0, balance - monthly_payment)

    return max(0.0, balance)


def calculate_mortgage_principal_balance(
    db: Session,
    debt: Debt,
    as_of_date: date | None = None,
) -> float:
    if debt.debt_type != "mortgage":
        return debt.current_balance or 0.0

    if not debt.original_amount:
        return debt.current_balance or 0.0

    as_of_date = as_of_date or date.today()
    if debt.start_date and as_of_date < debt.start_date:
        return 0.0
    payments = _collect_principal_payments(db, debt)
    principal_paid = sum(
        entry.principal
        for entry in payments
        if entry.payment_date and entry.payment_date <= as_of_date
    )
    return max(0.0, float(debt.original_amount) - principal_paid)


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
    today = today or date.today()

    if debt.debt_type == "credit_card":
        return {_month_end(today): debt.current_balance or 0.0}

    if not debt.original_amount or not debt.start_date:
        return {}

    accrue_interest = _should_accrue_interest(debt)
    annual_rate = _annual_rate_decimal(debt) if accrue_interest else 0.0
    monthly_rate = _monthly_rate(annual_rate) if accrue_interest else 0.0
    payments = _collect_principal_payments(db, debt)
    payments_by_month = _payments_by_month(payments)
    start_month = _month_start(debt.start_date)
    balance = float(debt.original_amount)
    balance_map: Dict[date, float] = {}

    for month_start in _iter_months(start_month, end_month):
        month_end = _month_end(month_start)
        if month_end < debt.start_date:
            balance_map[month_end] = 0.0
            continue

        if month_end <= today:
            if accrue_interest:
                balance += balance * monthly_rate
            month_key = (month_start.year, month_start.month)
            principal_paid = sum(
                entry.principal for entry in payments_by_month.get(month_key, [])
            )
            balance = max(0.0, balance - principal_paid)
        else:
            if accrue_interest:
                interest = balance * monthly_rate
                balance += interest
                if debt.monthly_payment and balance > 0:
                    principal_paid = max(0.0, debt.monthly_payment - interest)
                    balance = max(0.0, balance - principal_paid)
            else:
                if debt.monthly_payment and balance > 0:
                    balance = max(0.0, balance - debt.monthly_payment)

        balance_map[month_end] = max(0.0, balance)

    return balance_map
