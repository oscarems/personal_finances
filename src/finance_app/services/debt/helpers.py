"""
Debt calculation helpers — extracted from api/debts.py.
Pure business logic, no HTTP/FastAPI dependencies.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

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
    principal: Optional[float] = None,
    interest: Optional[float] = None,
    fees: Optional[float] = None,
) -> float:
    if principal is not None:
        return max(0.0, principal)
    interest = interest or 0.0
    fees = fees or 0.0
    return max(0.0, amount - interest - fees)


def calculate_loan_current_balance(debt: Debt, db: Session) -> float:
    if debt.debt_type not in {"mortgage", "credit_loan"}:
        return debt.current_balance
    return calculate_scheduled_principal_balance(debt=debt, as_of_date=date.today())


def payment_source_label(transaction_id: Optional[int]) -> str:
    return "transaccion" if transaction_id else "presupuesto"


def get_credit_card_current_balance(debt: Debt) -> float:
    account_balance = debt.account.balance if debt.account else 0.0
    return max(0.0, -(account_balance or 0.0))


def build_mortgage_payment_history(debt: Debt, db: Session) -> List[dict]:
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

    payments: List[dict] = []

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

    if not payments:
        return []

    payments.sort(key=lambda entry: (date.fromisoformat(entry["payment_date"]), entry["id"] or 0))

    balance = debt.original_amount if debt.original_amount is not None else (debt.current_balance or 0.0)
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


def debt_to_dict_with_calculated_balance(
    debt: Debt,
    db: Session,
    include_payments: bool = False,
    amortization_map: dict[int, DebtAmortizationMonthly] | None = None,
) -> dict:
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
