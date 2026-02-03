from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, Optional, Tuple

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from finance_app.models import Debt, DebtAmortizationMonthly, DebtPayment, MortgagePaymentAllocation


@dataclass(frozen=True)
class PaymentBreakdown:
    principal: float
    interest: float
    total: float


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _month_end(day: date) -> date:
    return day.replace(day=1) + relativedelta(months=1) - relativedelta(days=1)


def _iter_months(start_month: date, end_month: date) -> Iterable[date]:
    current = start_month
    while current <= end_month:
        yield current
        current = current + relativedelta(months=1)


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


def _monthly_rate(annual_rate: float) -> float:
    if not annual_rate:
        return 0.0
    return (1 + annual_rate) ** (1 / 12) - 1


def _payment_principal_from_debt_payment(payment: DebtPayment) -> float:
    if payment.principal is not None:
        return payment.principal
    interest = payment.interest or 0.0
    fees = payment.fees or 0.0
    amount = payment.amount or 0.0
    return max(0.0, amount - interest - fees)


def _collect_payment_breakdown(db: Session, debt: Debt) -> Dict[Tuple[int, int], PaymentBreakdown]:
    breakdown: Dict[Tuple[int, int], PaymentBreakdown] = {}

    allocations = db.query(MortgagePaymentAllocation).filter_by(loan_id=debt.id).all()
    allocation_transaction_ids = {
        allocation.transaction_id for allocation in allocations if allocation.transaction_id
    }

    payments = db.query(DebtPayment).filter_by(debt_id=debt.id).all()

    def _bucket(key: Tuple[int, int]) -> PaymentBreakdown:
        if key not in breakdown:
            breakdown[key] = PaymentBreakdown(0.0, 0.0, 0.0)
        return breakdown[key]

    for payment in payments:
        if not payment.payment_date:
            continue
        if payment.transaction_id and payment.transaction_id in allocation_transaction_ids:
            continue
        key = (payment.payment_date.year, payment.payment_date.month)
        principal = _payment_principal_from_debt_payment(payment)
        interest = payment.interest or 0.0
        amount = payment.amount or 0.0
        current = _bucket(key)
        breakdown[key] = PaymentBreakdown(
            principal=current.principal + principal,
            interest=current.interest + interest,
            total=current.total + amount,
        )

    for allocation in allocations:
        if not allocation.payment_date:
            continue
        key = (allocation.payment_date.year, allocation.payment_date.month)
        principal = float(allocation.principal_paid or 0.0) + float(allocation.extra_principal_paid or 0.0)
        interest = float(allocation.interest_paid or 0.0)
        total = principal + interest + float(allocation.fees_paid or 0.0) + float(allocation.escrow_paid or 0.0)
        current = _bucket(key)
        breakdown[key] = PaymentBreakdown(
            principal=current.principal + principal,
            interest=current.interest + interest,
            total=current.total + total,
        )

    return breakdown


def _infer_monthly_payment(
    payments_by_month: Dict[Tuple[int, int], PaymentBreakdown],
    today: date,
    months: int = 6,
) -> float:
    end_month = _month_start(today) - relativedelta(months=1)
    totals = []
    for offset in range(months):
        month = end_month - relativedelta(months=offset)
        total = payments_by_month.get((month.year, month.month), PaymentBreakdown(0.0, 0.0, 0.0)).total
        if total > 0:
            totals.append(total)
    if not totals:
        return 0.0
    return sum(totals) / len(totals)


def _calculate_month_entry(
    debt: Debt,
    month_start: date,
    balance: float,
    payments_by_month: Dict[Tuple[int, int], PaymentBreakdown],
    inferred_payment: float,
    current_month: date,
    monthly_rate: float,
    accrue_interest: bool,
) -> tuple[dict, float]:
    month_end = _month_end(month_start)
    principal_start = balance
    interest_accrued = principal_start * monthly_rate if accrue_interest else 0.0
    month_key = (month_start.year, month_start.month)
    payment_data = payments_by_month.get(month_key)

    if month_start <= current_month:
        total_payment = payment_data.total if payment_data else 0.0
        interest_payment = payment_data.interest if payment_data else 0.0
        if not payment_data and total_payment <= 0:
            interest_payment = 0.0
        if payment_data and interest_payment <= 0 and accrue_interest and total_payment > 0:
            interest_payment = min(total_payment, interest_accrued)
        principal_payment = payment_data.principal if payment_data else 0.0
        if principal_payment <= 0 and total_payment > 0:
            principal_payment = max(0.0, total_payment - interest_payment)
        status = "pagado"
    else:
        payment_total = debt.monthly_payment or inferred_payment or 0.0
        interest_payment = interest_accrued if accrue_interest else 0.0
        principal_payment = (
            max(0.0, payment_total - interest_payment) if accrue_interest else payment_total
        )
        total_payment = payment_total
        status = "proyeccion"

    if accrue_interest:
        balance += interest_accrued

    if principal_payment > balance:
        principal_payment = balance
    balance = max(0.0, balance - principal_payment)

    if total_payment <= 0:
        total_payment = principal_payment + interest_payment

    interest_rate_calculated = (
        (interest_payment / principal_start) * 100 if principal_start > 0 and interest_payment > 0 else 0.0
    )

    entry = {
        "month_start": month_start,
        "principal_payment": round(principal_payment, 6),
        "interest_payment": round(interest_payment, 6),
        "total_payment": round(total_payment, 6),
        "principal_remaining": round(balance, 6),
        "interest_rate_calculated": round(interest_rate_calculated, 6),
        "status": status,
    }
    return entry, balance


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
    for debt in debts:
        if debt.debt_type == "credit_card":
            continue
        debt_start = debt.start_date or start_month
        calculation_start = _month_start(debt_start)
        payments_by_month = _collect_payment_breakdown(db, debt)
        inferred_payment = _infer_monthly_payment(payments_by_month, today)
        annual_rate = _annual_rate_decimal(debt)
        accrue_interest = debt.debt_type != "mortgage"
        monthly_rate = _monthly_rate(annual_rate) if accrue_interest else 0.0

        existing = db.query(DebtAmortizationMonthly).filter(
            DebtAmortizationMonthly.debt_id == debt.id,
            DebtAmortizationMonthly.as_of_date >= start_month,
            DebtAmortizationMonthly.as_of_date <= end_month,
        ).all()
        existing_by_date = {entry.as_of_date: entry for entry in existing}

        balance = debt.original_amount if debt.original_amount is not None else (debt.current_balance or 0.0)

        for month_start in _iter_months(calculation_start, end_month):
            month_end = _month_end(month_start)
            if month_end < debt_start:
                continue
            entry, balance = _calculate_month_entry(
                debt=debt,
                month_start=month_start,
                balance=balance,
                payments_by_month=payments_by_month,
                inferred_payment=inferred_payment,
                current_month=current_month,
                monthly_rate=monthly_rate,
                accrue_interest=accrue_interest,
            )
            if month_start < start_month:
                continue
            if month_start in existing_by_date:
                continue
            db.add(DebtAmortizationMonthly(
                debt_id=debt.id,
                snapshot_month=month_start.strftime("%Y-%m"),
                as_of_date=month_start,
                currency_code=debt.currency_code,
                principal_payment=entry["principal_payment"],
                interest_payment=entry["interest_payment"],
                total_payment=entry["total_payment"],
                principal_remaining=entry["principal_remaining"],
                interest_rate_calculated=entry["interest_rate_calculated"],
                status=entry["status"],
            ))

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
