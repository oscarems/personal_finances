"""
Debt calculation helpers -- extracted from api/debts.py.
Pure business logic, no HTTP/FastAPI dependencies.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from finance_app.models import (
    Debt,
    DebtAmortizationMonthly,
    DebtPayment,
    MortgagePaymentAllocation,
)
from finance_app.services.debt.balance_service import (
    calculate_scheduled_principal_balance,
)
from finance_app.services.debt.amortization_service import (
    ensure_debt_amortization_records,
    fetch_amortization_for_month,
)


def payment_principal_amount(payment: DebtPayment) -> float:
    """Extract the principal portion from a debt payment.

    Falls back to ``amount - interest - fees`` when ``principal`` is not set.

    Args:
        payment: Debt payment record.

    Returns:
        Principal amount (always >= 0).
    """
    if payment.principal is not None:
        return max(0.0, payment.principal)
    if payment.amount is None:
        return 0.0
    interest = payment.interest or 0.0
    fees = payment.fees or 0.0
    principal = payment.amount - interest - fees
    return max(0.0, principal)


def calculate_principal_from_components(
    amount: float,
    principal: float | None = None,
    interest: float | None = None,
    fees: float | None = None,
) -> float:
    """Derive the principal from explicit components or by subtraction.

    Args:
        amount: Total payment amount.
        principal: Explicit principal, if provided.
        interest: Interest portion.
        fees: Fee portion.

    Returns:
        Principal amount (always >= 0).
    """
    if principal is not None:
        return max(0.0, principal)
    interest = interest or 0.0
    fees = fees or 0.0
    return max(0.0, amount - interest - fees)


def calculate_loan_current_balance(debt: Debt, db: Session) -> float:
    """Return the current balance for a mortgage or credit_loan debt.

    Uses the scheduled amortization plan to calculate the balance as of today.

    Args:
        debt: Debt model instance.
        db: Database session.

    Returns:
        Current balance.  Falls back to ``debt.current_balance`` for
        unsupported debt types.
    """
    if debt.debt_type not in {"mortgage", "credit_loan"}:
        return debt.current_balance
    return calculate_scheduled_principal_balance(debt=debt, as_of_date=date.today())


def payment_source_label(transaction_id: int | None) -> str:
    """Return a human-readable label for the payment source.

    Args:
        transaction_id: Transaction ID linked to the payment, or None.

    Returns:
        ``'transaccion'`` if linked, ``'presupuesto'`` otherwise.
    """
    return "transaccion" if transaction_id else "presupuesto"


def get_credit_card_current_balance(debt: Debt) -> float:
    """Derive credit-card debt balance from the linked account balance.

    Credit cards show the negative account balance as positive debt.

    Args:
        debt: Debt model instance with ``debt_type == 'credit_card'``.

    Returns:
        Current credit-card balance (always >= 0).
    """
    account_balance = debt.account.balance if debt.account else 0.0
    return max(0.0, -(account_balance or 0.0))


def _build_debt_payment_entries(debt: Debt, db: Session) -> list[dict]:
    """Collect DebtPayment records that are not already covered by allocations.

    Args:
        debt: Debt model instance.
        db: Database session.

    Returns:
        List of payment entry dicts.
    """
    allocations = db.query(MortgagePaymentAllocation).filter_by(loan_id=debt.id).order_by(
        MortgagePaymentAllocation.payment_date.asc(),
        MortgagePaymentAllocation.id.asc()
    ).all()

    allocation_transaction_ids = {
        allocation.transaction_id for allocation in allocations if allocation.transaction_id
    }

    debt_payments = db.query(DebtPayment).filter_by(debt_id=debt.id).order_by(
        DebtPayment.payment_date.asc(),
        DebtPayment.id.asc()
    ).all()

    payments: list[dict] = []

    for payment in debt_payments:
        if payment.transaction_id and payment.transaction_id in allocation_transaction_ids:
            continue
        principal = payment_principal_amount(payment)
        payments.append({
            "id": payment.id,
            "debt_id": payment.debt_id,
            "transaction_id": payment.transaction_id,
            "payment_date": payment.payment_date.isoformat() if payment.payment_date else None,
            "amount": payment.amount,
            "principal": principal,
            "interest": payment.interest,
            "fees": payment.fees or 0.0,
            "balance_after": None,
            "notes": payment.notes,
            "payment_source": payment_source_label(payment.transaction_id),
        })

    return payments, allocations


def _build_allocation_entries(allocations: list) -> list[dict]:
    """Convert MortgagePaymentAllocation rows into payment entry dicts.

    Args:
        allocations: List of MortgagePaymentAllocation instances.

    Returns:
        List of payment entry dicts.
    """
    payments: list[dict] = []
    for allocation in allocations:
        principal_paid = float(allocation.principal_paid or 0.0) + float(allocation.extra_principal_paid or 0.0)
        interest_paid = float(allocation.interest_paid or 0.0)
        fees_paid = float(allocation.fees_paid or 0.0)
        escrow_paid = float(allocation.escrow_paid or 0.0)
        amount = principal_paid + interest_paid + fees_paid + escrow_paid
        payments.append({
            "id": allocation.id,
            "debt_id": allocation.loan_id,
            "transaction_id": allocation.transaction_id,
            "payment_date": allocation.payment_date.isoformat() if allocation.payment_date else None,
            "amount": amount,
            "principal": principal_paid,
            "interest": interest_paid,
            "fees": fees_paid + escrow_paid,
            "balance_after": None,
            "notes": allocation.notes,
            "payment_source": "transaccion",
        })
    return payments


def _apply_running_balance(payments: list[dict], original_amount: float) -> list[dict]:
    """Sort payments chronologically and compute running balance_after.

    Also adds Spanish alias fields expected by the UI.

    Args:
        payments: List of payment entry dicts (mutated in place).
        original_amount: Starting debt balance.

    Returns:
        The sorted payments list with balance_after populated.
    """
    payments.sort(key=lambda entry: (date.fromisoformat(entry["payment_date"]), entry["id"] or 0))

    balance = original_amount
    for entry in payments:
        principal = entry.get("principal") or 0.0
        balance = max(0.0, balance - principal)
        entry["balance_after"] = balance
        entry["fecha"] = entry["payment_date"]
        entry["monto_total_pagado"] = entry["amount"]
        entry["monto_principal"] = entry["principal"]
        entry["monto_interes"] = entry["interest"]
        entry["saldo_restante_despues_del_pago"] = entry["balance_after"]
        entry["fuente_del_pago"] = entry["payment_source"]

    return payments


def build_mortgage_payment_history(debt: Debt, db: Session) -> list[dict]:
    """Build a unified, chronologically sorted payment history for a mortgage.

    Merges DebtPayment records and MortgagePaymentAllocation records,
    deduplicating by transaction_id, then computes a running balance.

    Args:
        debt: Debt model instance.
        db: Database session.

    Returns:
        List of payment dicts with running ``balance_after``.
    """
    debt_entries, allocations = _build_debt_payment_entries(debt, db)
    allocation_entries = _build_allocation_entries(allocations)

    payments = debt_entries + allocation_entries
    if not payments:
        return []

    original_balance = debt.original_amount if debt.original_amount is not None else (debt.current_balance or 0.0)
    return _apply_running_balance(payments, original_balance)


def debt_to_dict_with_calculated_balance(
    debt: Debt,
    db: Session,
    include_payments: bool = False,
    amortization_map: dict[int, DebtAmortizationMonthly] | None = None,
) -> dict:
    """Serialize a Debt to a dict with a freshly calculated ``current_balance``.

    For credit cards, the balance is derived from the linked account.
    For loans, the amortization records or scheduled balance is used.

    Args:
        debt: Debt model instance.
        db: Database session.
        include_payments: Whether to include payment history in the output.
        amortization_map: Pre-fetched amortization records keyed by debt_id.

    Returns:
        Dict representation of the debt with ``current_balance`` and
        ``paid_percentage`` fields.
    """
    data = debt.to_dict(include_payments=include_payments)
    if debt.debt_type == "credit_card":
        data["current_balance"] = get_credit_card_current_balance(debt)
        if debt.original_amount and debt.original_amount > 0:
            data["paid_percentage"] = ((debt.original_amount - data["current_balance"]) / debt.original_amount) * 100
        return data

    today = date.today()
    current_month = today.replace(day=1)
    current_record = None
    if amortization_map is not None:
        current_record = amortization_map.get(debt.id)
    else:
        ensure_debt_amortization_records(db, current_month, current_month)
        amortization_map = fetch_amortization_for_month(db, current_month, [debt.id])
        current_record = amortization_map.get(debt.id)
    if debt.debt_type in {"mortgage", "credit_loan"}:
        calculated_balance = calculate_loan_current_balance(debt, db)
    elif current_record:
        calculated_balance = current_record.principal_remaining
    else:
        calculated_balance = debt.current_balance or 0.0
    data["current_balance"] = calculated_balance
    if debt.original_amount and debt.original_amount > 0:
        data["paid_percentage"] = ((debt.original_amount - calculated_balance) / debt.original_amount) * 100
    return data
