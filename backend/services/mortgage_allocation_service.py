from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from backend.models import Currency, Debt, MortgagePaymentAllocation, Transaction


_ZERO = Decimal("0")


def _to_decimal(value) -> Decimal:
    if value is None:
        return _ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _quantize(amount: Decimal, decimals: int) -> Decimal:
    exponent = Decimal("1").scaleb(-decimals)
    return amount.quantize(exponent, rounding=ROUND_HALF_UP)


def _normalize_annual_rate(rate_value) -> Decimal:
    if rate_value is None:
        return _ZERO
    rate = _to_decimal(rate_value)
    if rate > Decimal("1"):
        rate = rate / Decimal("100")
    return rate


def _days_between(start: date, end: date) -> int:
    if not start or not end:
        return 0
    return max(0, (end - start).days)


def _currency_from_transaction(db: Session, transaction: Transaction) -> Currency:
    currency = db.query(Currency).get(transaction.currency_id)
    if not currency:
        raise ValueError("Transaction currency not found.")
    return currency


def _get_loan_for_update(db: Session, loan_id: int) -> Debt:
    loan = db.query(Debt).filter(Debt.id == loan_id).with_for_update().one_or_none()
    if not loan:
        raise ValueError("Mortgage loan not found.")
    if loan.debt_type != "mortgage":
        raise ValueError("Loan is not a mortgage.")
    return loan


def _get_currency_decimals(db: Session, loan: Debt, transaction: Transaction) -> int:
    currency = _currency_from_transaction(db, transaction)
    if currency.code != loan.currency_code:
        raise ValueError("Transaction currency does not match mortgage currency.")
    return currency.decimals or 2


def _get_payment_amount(transaction: Transaction) -> Decimal:
    raw_amount = transaction.original_amount if transaction.original_amount is not None else transaction.amount
    payment_amount = _to_decimal(raw_amount).copy_abs()
    if payment_amount <= _ZERO:
        raise ValueError("Mortgage payment amount must be greater than zero.")
    return payment_amount


def _current_balances(loan: Debt) -> Tuple[Decimal, Decimal]:
    principal_balance = loan.principal_balance
    if principal_balance is None:
        base = loan.current_balance if loan.current_balance is not None else loan.original_amount
        principal_balance = _to_decimal(base)
    interest_balance = _to_decimal(loan.interest_balance)
    return principal_balance, interest_balance


def _calculate_accrued_interest(
    principal_balance: Decimal,
    annual_rate: Decimal,
    last_accrual_date: Optional[date],
    payment_date: date,
    decimals: int
) -> Decimal:
    if principal_balance <= _ZERO or annual_rate <= _ZERO or not last_accrual_date:
        return _ZERO
    days = _days_between(last_accrual_date, payment_date)
    if days <= 0:
        return _ZERO
    interest = principal_balance * annual_rate * Decimal(days) / Decimal("365")
    return _quantize(interest, decimals)


def _apply_balances(
    loan: Debt,
    principal_balance: Decimal,
    interest_balance: Decimal,
    payment_date: date,
    decimals: int
) -> None:
    principal_balance = max(_ZERO, principal_balance)
    interest_balance = max(_ZERO, interest_balance)
    loan.principal_balance = _quantize(principal_balance, decimals)
    loan.interest_balance = _quantize(interest_balance, decimals)
    loan.last_accrual_date = payment_date
    loan.current_balance = float(loan.principal_balance + loan.interest_balance)


def apply_mortgage_payment_allocation(
    db: Session,
    transaction: Transaction,
    allocation: dict
) -> MortgagePaymentAllocation:
    loan_id = allocation.get("loan_id")
    if not loan_id:
        raise ValueError("Mortgage allocation requires loan_id.")

    existing = db.query(MortgagePaymentAllocation).filter_by(transaction_id=transaction.id).one_or_none()
    if existing:
        if existing.loan_id != loan_id:
            raise ValueError("Transaction already allocated to another mortgage loan.")
        return existing

    loan = _get_loan_for_update(db, loan_id)
    decimals = _get_currency_decimals(db, loan, transaction)
    payment_amount = _quantize(_get_payment_amount(transaction), decimals)

    payment_date = allocation.get("payment_date") or transaction.date
    if not isinstance(payment_date, date):
        raise ValueError("payment_date must be a date.")

    fees_paid = _quantize(_to_decimal(allocation.get("fees_paid")), decimals)
    escrow_paid = _quantize(_to_decimal(allocation.get("escrow_paid")), decimals)
    if fees_paid < _ZERO or escrow_paid < _ZERO:
        raise ValueError("Fees and escrow must be zero or positive.")

    remaining_after_fees = payment_amount - fees_paid - escrow_paid
    if remaining_after_fees < _ZERO:
        raise ValueError("Fees and escrow exceed payment amount.")

    mode = allocation.get("mode", "auto")
    if mode not in {"auto", "manual"}:
        raise ValueError("Mortgage allocation mode must be 'auto' or 'manual'.")

    principal_balance, interest_balance = _current_balances(loan)
    if principal_balance <= _ZERO:
        raise ValueError("Mortgage principal balance is already zero.")

    annual_rate = _normalize_annual_rate(loan.annual_interest_rate or loan.interest_rate)
    last_accrual_date = loan.last_accrual_date or loan.start_date or payment_date
    if payment_date < last_accrual_date:
        raise ValueError("payment_date cannot be earlier than last accrual date.")

    accrued_interest = _calculate_accrued_interest(
        principal_balance,
        annual_rate,
        last_accrual_date,
        payment_date,
        decimals
    )
    interest_balance = _quantize(interest_balance + accrued_interest, decimals)

    if mode == "manual":
        interest_paid = _quantize(_to_decimal(allocation.get("interest_paid")), decimals)
        principal_paid = _quantize(_to_decimal(allocation.get("principal_paid")), decimals)
        extra_principal_paid = _quantize(_to_decimal(allocation.get("extra_principal_paid")), decimals)
        if min(interest_paid, principal_paid, extra_principal_paid) < _ZERO:
            raise ValueError("Mortgage allocation amounts cannot be negative.")
        total_allocated = (
            interest_paid + principal_paid + extra_principal_paid + fees_paid + escrow_paid
        )
        if total_allocated != payment_amount:
            raise ValueError("Allocation total must equal mortgage payment amount.")
        if principal_paid + extra_principal_paid > principal_balance:
            raise ValueError("Principal allocation exceeds remaining balance.")
    else:
        interest_paid = min(interest_balance, remaining_after_fees)
        remaining_after_interest = remaining_after_fees - interest_paid

        monthly_payment = _to_decimal(loan.monthly_payment)
        if monthly_payment > _ZERO:
            scheduled_principal = max(
                _ZERO,
                monthly_payment - interest_paid - fees_paid - escrow_paid
            )
            principal_paid = min(remaining_after_interest, scheduled_principal, principal_balance)
            remaining_after_principal = remaining_after_interest - principal_paid
            extra_principal_paid = min(
                remaining_after_principal,
                principal_balance - principal_paid
            )
        else:
            principal_paid = min(remaining_after_interest, principal_balance)
            remaining_after_principal = remaining_after_interest - principal_paid
            extra_principal_paid = min(
                remaining_after_principal,
                principal_balance - principal_paid
            )

        interest_paid = _quantize(interest_paid, decimals)
        principal_paid = _quantize(principal_paid, decimals)
        extra_principal_paid = _quantize(extra_principal_paid, decimals)
        total_allocated = (
            interest_paid + principal_paid + extra_principal_paid + fees_paid + escrow_paid
        )
        if total_allocated != payment_amount:
            raise ValueError("Mortgage payment allocation does not match payment amount.")
        if remaining_after_principal - extra_principal_paid > _ZERO:
            raise ValueError("Mortgage payment exceeds remaining principal balance.")

    interest_balance = _quantize(max(_ZERO, interest_balance - interest_paid), decimals)
    principal_balance = _quantize(
        max(_ZERO, principal_balance - principal_paid - extra_principal_paid),
        decimals
    )
    _apply_balances(loan, principal_balance, interest_balance, payment_date, decimals)

    allocation_row = MortgagePaymentAllocation(
        transaction_id=transaction.id,
        loan_id=loan.id,
        payment_date=payment_date,
        period=allocation.get("period"),
        notes=allocation.get("notes"),
        interest_paid=interest_paid,
        principal_paid=principal_paid,
        fees_paid=fees_paid,
        escrow_paid=escrow_paid,
        extra_principal_paid=extra_principal_paid,
        currency_code=loan.currency_code
    )
    db.add(allocation_row)
    return allocation_row


def rebuild_mortgage_balances(db: Session, loan: Debt) -> None:
    allocations = db.query(MortgagePaymentAllocation).filter_by(
        loan_id=loan.id
    ).order_by(MortgagePaymentAllocation.payment_date.asc(), MortgagePaymentAllocation.id.asc()).all()

    transaction = allocations[0].transaction if allocations else None
    if transaction:
        decimals = _get_currency_decimals(db, loan, transaction)
    else:
        currency = db.query(Currency).filter_by(code=loan.currency_code).first()
        decimals = currency.decimals if currency else 2

    principal_balance = _to_decimal(loan.original_amount or loan.current_balance or 0)
    interest_balance = _ZERO
    annual_rate = _normalize_annual_rate(loan.annual_interest_rate or loan.interest_rate)
    last_accrual_date = loan.start_date

    for allocation in allocations:
        payment_date = allocation.payment_date
        accrued_interest = _calculate_accrued_interest(
            principal_balance,
            annual_rate,
            last_accrual_date or payment_date,
            payment_date,
            decimals
        )
        interest_balance = _quantize(interest_balance + accrued_interest, decimals)
        interest_balance = _quantize(
            max(_ZERO, interest_balance - _to_decimal(allocation.interest_paid)),
            decimals
        )
        principal_reduction = _to_decimal(allocation.principal_paid) + _to_decimal(allocation.extra_principal_paid)
        principal_balance = _quantize(
            max(_ZERO, principal_balance - principal_reduction),
            decimals
        )
        last_accrual_date = payment_date

    if allocations:
        loan.last_accrual_date = last_accrual_date
    _apply_balances(loan, principal_balance, interest_balance, last_accrual_date or loan.start_date or date.today(), decimals)
