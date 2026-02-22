"""
Debts API endpoints - Gestión de deudas
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from finance_app.database import get_db
from finance_app.models import (
    Debt,
    DebtAmortizationMonthly,
    DebtPayment,
    Account,
    MortgagePaymentAllocation,
)
from finance_app.services.debt_balance_service import (
    calculate_mortgage_principal_balance,
    calculate_scheduled_principal_balance,
    refresh_mortgage_current_balance,
)
from finance_app.services.debt_amortization_service import (
    ensure_debt_amortization_records,
    fetch_amortization_for_month,
    fetch_amortization_range,
)
from finance_app.services.amortization_engine import AmortizationEngine, UnsupportedAmortizationTypeError
from domain.fx.service import convert_to_cop

router = APIRouter()


def _payment_principal_amount(payment: DebtPayment) -> float:
    if payment.principal is not None:
        return max(0.0, payment.principal)
    if payment.amount is None:
        return 0.0
    interest = payment.interest or 0.0
    fees = payment.fees or 0.0
    principal = payment.amount - interest - fees
    return max(0.0, principal)


def _calculate_principal_amount(payment: DebtPaymentCreate) -> float:
    if payment.principal is not None:
        return max(0.0, payment.principal)
    interest = payment.interest or 0.0
    fees = payment.fees or 0.0
    principal = payment.amount - interest - fees
    return max(0.0, principal)


def _calculate_mortgage_current_balance(debt: Debt, db: Session) -> float:
    if debt.debt_type != "mortgage":
        return debt.current_balance
    return calculate_scheduled_principal_balance(debt=debt, as_of_date=date.today())


def _calculate_loan_current_balance(debt: Debt, db: Session) -> float:
    if debt.debt_type not in {"mortgage", "credit_loan"}:
        return debt.current_balance
    return calculate_scheduled_principal_balance(debt=debt, as_of_date=date.today())


def _payment_source_label(transaction_id: Optional[int]) -> str:
    return "transaccion" if transaction_id else "presupuesto"


def _get_credit_card_current_balance(debt: Debt) -> float:
    account_balance = debt.account.balance if debt.account else 0.0
    return max(0.0, -(account_balance or 0.0))


def _build_mortgage_payment_history(debt: Debt, db: Session) -> List[dict]:
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
        principal = _payment_principal_amount(payment)
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
            "payment_source": _payment_source_label(payment.transaction_id),
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


def _debt_to_dict_with_calculated_balance(
    debt: Debt,
    db: Session,
    include_payments: bool = False,
    amortization_map: dict[int, DebtAmortizationMonthly] | None = None,
) -> dict:
    data = debt.to_dict(include_payments=include_payments)
    if debt.debt_type == "credit_card":
        data["current_balance"] = _get_credit_card_current_balance(debt)
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
        calculated_balance = _calculate_loan_current_balance(debt, db)
    elif current_record:
        calculated_balance = current_record.principal_remaining
    else:
        calculated_balance = debt.current_balance or 0.0
    data["current_balance"] = calculated_balance
    if debt.original_amount and debt.original_amount > 0:
        data["paid_percentage"] = ((debt.original_amount - calculated_balance) / debt.original_amount) * 100
    return data


# Pydantic Schemas
class DebtCreate(BaseModel):
    """Schema for creating a debt"""
    account_id: int
    name: str
    debt_type: str  # 'credit_card', 'credit_loan', 'mortgage'
    category_id: Optional[int] = None
    currency_code: str = 'COP'
    original_amount: float
    current_balance: Optional[float] = None
    credit_limit: Optional[float] = None
    interest_rate: Optional[float] = None
    monthly_payment: Optional[float] = None
    minimum_payment: Optional[float] = None
    loan_years: Optional[int] = None
    start_date: date
    due_date: Optional[date] = None
    payment_day: Optional[int] = None
    institution: Optional[str] = None
    account_number: Optional[str] = None
    notes: Optional[str] = None
    has_insurance: Optional[bool] = False


class DebtUpdate(BaseModel):
    """Schema for updating a debt"""
    name: Optional[str] = None
    category_id: Optional[int] = None
    current_balance: Optional[float] = None
    credit_limit: Optional[float] = None
    interest_rate: Optional[float] = None
    monthly_payment: Optional[float] = None
    minimum_payment: Optional[float] = None
    loan_years: Optional[int] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    payment_day: Optional[int] = None
    institution: Optional[str] = None
    account_number: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    is_consolidated: Optional[bool] = None
    has_insurance: Optional[bool] = None


class DebtPaymentCreate(BaseModel):
    """Schema for creating a debt payment"""
    payment_date: date
    amount: float
    principal: Optional[float] = None
    interest: Optional[float] = None
    fees: Optional[float] = None
    notes: Optional[str] = None
    transaction_id: Optional[int] = None


@router.get("/")
def get_debts(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    debt_type: Optional[str] = Query(None, description="Filter by debt type"),
    db: Session = Depends(get_db)
):
    """
    Get all debts with optional filters

    Args:
        is_active: Filter by active/inactive debts
        debt_type: Filter by debt type (credit_card, credit_loan, mortgage)

    Returns:
        List of debts with calculations
    """
    query = db.query(Debt)

    if is_active is not None:
        query = query.filter(Debt.is_active == is_active)

    if debt_type:
        query = query.filter(Debt.debt_type == debt_type)

    debts = query.all()
    today = date.today()
    current_month = today.replace(day=1)
    debt_ids = [debt.id for debt in debts if debt.debt_type != "credit_card"]
    amortization_map: dict[int, DebtAmortizationMonthly] = {}
    if debt_ids:
        ensure_debt_amortization_records(db, current_month, current_month)
        amortization_map = fetch_amortization_for_month(db, current_month, debt_ids)

    return [
        _debt_to_dict_with_calculated_balance(debt, db, amortization_map=amortization_map)
        for debt in debts
    ]


@router.get("/summary")
def get_debts_summary(db: Session = Depends(get_db)):
    """
    Get summary of all debts grouped by type and currency

    Returns:
        Summary with totals, averages, and statistics
    """
    debts = db.query(Debt).filter(Debt.is_active == True).all()
    today = date.today()
    current_month = today.replace(day=1)
    ensure_debt_amortization_records(db, current_month, current_month)
    amortization_map = fetch_amortization_for_month(db, current_month)
    eligible_debts = debts

    summary = {
        'total_debts': len(eligible_debts),
        'by_type': {},
        'by_currency': {},
        'total_original': {},
        'total_current': {},
        'total_paid': {},
        'average_interest_rate': 0,
        'total_monthly_payment': {},
        'debts_near_payoff': [],  # Deudas cerca de pagarse (< 10% restante)
        'high_interest_debts': []  # Deudas con interés alto (> 20%)
    }

    if not eligible_debts:
        return summary

    total_interest_sum = 0
    interest_count = 0

    for debt in eligible_debts:
        if debt.debt_type in {"mortgage", "credit_loan"}:
            current_balance = _calculate_loan_current_balance(debt, db)
        elif debt.debt_type == "credit_card":
            current_balance = _get_credit_card_current_balance(debt)
        else:
            record = amortization_map.get(debt.id)
            current_balance = float(record.principal_remaining) if record else (debt.current_balance or 0.0)

        # Group by type
        if debt.debt_type not in summary['by_type']:
            summary['by_type'][debt.debt_type] = {
                'count': 0,
                'total_balance': 0,
                'total_original': 0
            }
        summary['by_type'][debt.debt_type]['count'] += 1
        summary['by_type'][debt.debt_type]['total_balance'] += current_balance
        summary['by_type'][debt.debt_type]['total_original'] += debt.original_amount

        # Group by currency
        if debt.currency_code not in summary['by_currency']:
            summary['by_currency'][debt.currency_code] = {
                'count': 0,
                'total_balance': 0
            }
        summary['by_currency'][debt.currency_code]['count'] += 1
        summary['by_currency'][debt.currency_code]['total_balance'] += current_balance

        # Totals by currency
        if debt.currency_code not in summary['total_original']:
            summary['total_original'][debt.currency_code] = 0
            summary['total_current'][debt.currency_code] = 0
            summary['total_paid'][debt.currency_code] = 0
            summary['total_monthly_payment'][debt.currency_code] = 0

        summary['total_original'][debt.currency_code] += debt.original_amount
        summary['total_current'][debt.currency_code] += current_balance
        summary['total_paid'][debt.currency_code] += (debt.original_amount - current_balance)

        if debt.monthly_payment:
            summary['total_monthly_payment'][debt.currency_code] += debt.monthly_payment

        # Average interest rate
        if debt.interest_rate:
            total_interest_sum += debt.interest_rate
            interest_count += 1

        paid_percentage = 0
        if debt.original_amount and debt.original_amount > 0:
            paid_percentage = ((debt.original_amount - current_balance) / debt.original_amount) * 100

        # Debts near payoff
        if paid_percentage >= 90:
            summary['debts_near_payoff'].append({
                'id': debt.id,
                'name': debt.name,
                'remaining': current_balance,
                'percentage': paid_percentage
            })

        # High interest debts
        if debt.interest_rate and debt.interest_rate > 20:
            summary['high_interest_debts'].append({
                'id': debt.id,
                'name': debt.name,
                'interest_rate': debt.interest_rate,
                'balance': current_balance
            })

    if interest_count > 0:
        summary['average_interest_rate'] = total_interest_sum / interest_count

    return summary


@router.get("/{debt_id}")
def get_debt(debt_id: int, include_payments: bool = False, db: Session = Depends(get_db)):
    """
    Get a single debt by ID

    Args:
        debt_id: ID of the debt
        include_payments: Include payment history

    Returns:
        Debt details with optional payment history
    """
    debt = db.query(Debt).filter_by(id=debt_id).first()
    if not debt:
        raise HTTPException(status_code=404, detail="Debt not found")

    amortization_map = None
    if debt.debt_type != "credit_card":
        today = date.today()
        current_month = today.replace(day=1)
        ensure_debt_amortization_records(db, current_month, current_month)
        amortization_map = fetch_amortization_for_month(db, current_month, [debt.id])
    return _debt_to_dict_with_calculated_balance(
        debt,
        db,
        include_payments=include_payments,
        amortization_map=amortization_map,
    )


@router.post("/")
def create_debt(debt_data: DebtCreate, db: Session = Depends(get_db)):
    """
    Create a new debt

    Args:
        debt_data: Debt information

    Returns:
        Created debt
    """
    # Validate account exists
    account = db.query(Account).filter_by(id=debt_data.account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Validate debt type
    valid_types = ['credit_card', 'credit_loan', 'mortgage']
    if debt_data.debt_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid debt_type. Must be one of: {', '.join(valid_types)}"
        )

    # Create debt
    current_balance = debt_data.current_balance
    if debt_data.debt_type == "mortgage" and current_balance is None:
        current_balance = debt_data.original_amount
    if debt_data.debt_type != "mortgage" and current_balance is None:
        raise HTTPException(status_code=400, detail="Current balance is required for this debt type.")

    new_debt = Debt(
        account_id=debt_data.account_id,
        name=debt_data.name,
        debt_type=debt_data.debt_type,
        category_id=debt_data.category_id,
        currency_code=debt_data.currency_code,
        original_amount=debt_data.original_amount,
        current_balance=current_balance,
        credit_limit=debt_data.credit_limit,
        interest_rate=debt_data.interest_rate,
        monthly_payment=debt_data.monthly_payment,
        minimum_payment=debt_data.minimum_payment,
        loan_years=debt_data.loan_years,
        start_date=debt_data.start_date,
        due_date=debt_data.due_date,
        payment_day=debt_data.payment_day,
        institution=debt_data.institution,
        account_number=debt_data.account_number,
        notes=debt_data.notes,
        has_insurance=debt_data.has_insurance or False,
        is_active=True
    )

    db.add(new_debt)
    db.commit()
    db.refresh(new_debt)

    if account.type in {'credit_loan', 'mortgage'}:
        if debt_data.interest_rate is not None:
            account.interest_rate = debt_data.interest_rate
        if debt_data.monthly_payment is not None:
            account.monthly_payment = debt_data.monthly_payment
        if debt_data.original_amount is not None:
            account.original_amount = debt_data.original_amount
        if debt_data.loan_years is not None:
            account.loan_years = debt_data.loan_years
        account.loan_start_date = debt_data.start_date
        db.commit()

    return new_debt.to_dict()


@router.patch("/{debt_id}")
def update_debt(debt_id: int, debt_update: DebtUpdate, db: Session = Depends(get_db)):
    """
    Update a debt

    Args:
        debt_id: ID of the debt to update
        debt_update: Fields to update

    Returns:
        Updated debt
    """
    debt = db.query(Debt).filter_by(id=debt_id).first()
    if not debt:
        raise HTTPException(status_code=404, detail="Debt not found")

    # Update fields
    update_data = debt_update.dict(exclude_unset=True)
    if debt.debt_type == "mortgage" and "current_balance" in update_data:
        update_data.pop("current_balance")
    for field, value in update_data.items():
        setattr(debt, field, value)

    if debt.account and debt.account.type in {'credit_loan', 'mortgage'}:
        if debt_update.interest_rate is not None:
            debt.account.interest_rate = debt_update.interest_rate
        if debt_update.monthly_payment is not None:
            debt.account.monthly_payment = debt_update.monthly_payment
        if debt_update.current_balance is not None:
            debt.account.balance = debt_update.current_balance
        if debt_update.loan_years is not None:
            debt.account.loan_years = debt_update.loan_years
        if debt_update.start_date is not None:
            debt.account.loan_start_date = debt_update.start_date
        if debt_update.due_date is not None:
            debt.account.maturity_date = debt_update.due_date

    db.commit()
    db.refresh(debt)

    return _debt_to_dict_with_calculated_balance(debt, db)


@router.delete("/{debt_id}")
def delete_debt(debt_id: int, db: Session = Depends(get_db)):
    """
    Delete a debt

    Args:
        debt_id: ID of the debt to delete

    Returns:
        Success message
    """
    debt = db.query(Debt).filter_by(id=debt_id).first()
    if not debt:
        raise HTTPException(status_code=404, detail="Debt not found")

    debt_name = debt.name
    db.delete(debt)
    db.commit()

    return {
        "success": True,
        "message": f"Debt '{debt_name}' deleted successfully"
    }


def _parse_month(month_str: Optional[str], fallback: date) -> date:
    if not month_str:
        return fallback.replace(day=1)
    if len(month_str) == 7:
        return date.fromisoformat(f"{month_str}-01")
    return date.fromisoformat(month_str).replace(day=1)


def _iter_months(start_month: date, end_month: date) -> List[date]:
    months = []
    current = start_month.replace(day=1)
    end_month = end_month.replace(day=1)
    while current <= end_month:
        months.append(current)
        current = current + relativedelta(months=1)
    return months


@router.get("/timeline")
def get_debt_timeline(
    start: Optional[str] = None,
    end: Optional[str] = None,
    include_projected: bool = True,
    db: Session = Depends(get_db),
):
    """
    Return month-by-month principal timeline in COP.
    """
    today = date.today()
    start_month = _parse_month(start, today)
    end_month = _parse_month(end, today)
    months = _iter_months(start_month, end_month)

    current_month = today.replace(day=1)
    ensure_debt_amortization_records(db, start_month, end_month)

    debts = db.query(Debt).filter(Debt.debt_type != "credit_card").all()
    debt_ids = [debt.id for debt in debts]
    amortization_records = fetch_amortization_range(db, start_month, end_month, debt_ids)

    per_debt = {
        str(debt.id): {
            "name": debt.name,
            "currency_code": debt.currency_code,
            "principal_cop_by_month": [],
            "principal_original_by_month": [],
        }
        for debt in debts
    }

    totals_cop_by_month = []
    month_labels = []

    for month in months:
        month_labels.append(month.strftime("%Y-%m"))
        total_cop = 0.0
        for debt in debts:
            record = amortization_records.get((debt.id, month))
            if record:
                principal_original = float(record.principal_remaining)
                principal_cop = float(convert_to_cop(principal_original, debt.currency_code, month, db=db))
                total_cop += principal_cop
            else:
                principal_original = 0.0
                principal_cop = 0.0

            per_debt[str(debt.id)]["principal_cop_by_month"].append(round(principal_cop, 2))
            per_debt[str(debt.id)]["principal_original_by_month"].append(round(principal_original, 2))

        totals_cop_by_month.append(round(total_cop, 2))

    return {
        "months": month_labels,
        "totals_cop_by_month": totals_cop_by_month,
        "per_debt": per_debt,
    }


@router.get("/{debt_id}/schedule")
def get_debt_schedule(
    debt_id: int,
    mode: str = Query("hybrid", pattern="^(plan|actual|hybrid)$"),
    as_of: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    debt = db.query(Debt).filter_by(id=debt_id).first()
    if not debt:
        raise HTTPException(status_code=404, detail="Debt not found")

    engine = AmortizationEngine(db=db)
    try:
        schedule = engine.generate_schedule(debt, as_of=as_of, mode=mode)
        balance = engine.balance_as_of(debt, as_of or date.today(), mode=mode)
    except UnsupportedAmortizationTypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "debt_id": debt.id,
        "mode": mode,
        "as_of": (as_of or date.today()).isoformat(),
        "balance": balance,
        "schedule": [
            {
                **item,
                "date": item["date"].isoformat(),
            }
            for item in schedule
        ],
    }


# Debt Payments endpoints
@router.get("/{debt_id}/payments")
def get_debt_payments(debt_id: int, db: Session = Depends(get_db)):
    """
    Get all payments for a specific debt

    Args:
        debt_id: ID of the debt

    Returns:
        List of payments
    """
    debt = db.query(Debt).filter_by(id=debt_id).first()
    if not debt:
        raise HTTPException(status_code=404, detail="Debt not found")

    if debt.debt_type == "mortgage":
        payments = _build_mortgage_payment_history(debt, db)
        return sorted(
            payments,
            key=lambda payment: date.fromisoformat(payment["payment_date"]),
            reverse=True
        )

    payments = db.query(DebtPayment).filter_by(debt_id=debt_id).order_by(
        DebtPayment.payment_date.desc()
    ).all()
    payment_dicts = [payment.to_dict() for payment in payments]
    for entry in payment_dicts:
        entry["payment_source"] = _payment_source_label(entry.get("transaction_id"))
        entry["fecha"] = entry["payment_date"]
        entry["monto_total_pagado"] = entry["amount"]
        entry["monto_principal"] = entry["principal"]
        entry["monto_interes"] = entry["interest"]
        entry["saldo_restante_despues_del_pago"] = entry["balance_after"]
        entry["fuente_del_pago"] = entry["payment_source"]

    return payment_dicts


@router.post("/{debt_id}/payments")
def create_debt_payment(debt_id: int, payment_data: DebtPaymentCreate, db: Session = Depends(get_db)):
    """
    Record a payment for a debt

    Args:
        debt_id: ID of the debt
        payment_data: Payment information

    Returns:
        Created payment and updated debt
    """
    debt = db.query(Debt).filter_by(id=debt_id).first()
    if not debt:
        raise HTTPException(status_code=404, detail="Debt not found")

    principal_amount = _calculate_principal_amount(payment_data)
    # Calculate balance after payment (solo capital)
    if debt.debt_type == "mortgage":
        balance_after = None
    else:
        balance_after = debt.current_balance - principal_amount

    # Create payment record
    new_payment = DebtPayment(
        debt_id=debt_id,
        payment_date=payment_data.payment_date,
        amount=payment_data.amount,
        principal=payment_data.principal,
        interest=payment_data.interest,
        fees=payment_data.fees,
        balance_after=balance_after,
        notes=payment_data.notes,
        transaction_id=payment_data.transaction_id
    )

    db.add(new_payment)
    db.flush()

    # Update debt balance
    if debt.debt_type == "mortgage":
        debt.current_balance = refresh_mortgage_current_balance(db, debt, as_of_date=payment_data.payment_date)
        new_payment.balance_after = debt.current_balance
    else:
        debt.current_balance = balance_after

    # If debt is fully paid, mark as inactive
    if debt.current_balance <= 0:
        debt.is_active = False

    db.commit()
    db.refresh(new_payment)
    db.refresh(debt)

    return {
        "payment": new_payment.to_dict(),
        "debt": _debt_to_dict_with_calculated_balance(debt, db)
    }


@router.delete("/{debt_id}/payments/{payment_id}")
def delete_debt_payment(debt_id: int, payment_id: int, db: Session = Depends(get_db)):
    """
    Delete a debt payment and restore the debt balance

    Args:
        debt_id: ID of the debt
        payment_id: ID of the payment to delete

    Returns:
        Success message
    """
    payment = db.query(DebtPayment).filter_by(
        id=payment_id,
        debt_id=debt_id
    ).first()

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    debt = db.query(Debt).filter_by(id=debt_id).first()

    principal_amount = payment.principal
    if principal_amount is None and payment.amount is not None:
        interest = payment.interest or 0.0
        fees = payment.fees or 0.0
        principal_amount = payment.amount - interest - fees
    principal_amount = max(0.0, principal_amount or 0.0)

    db.delete(payment)
    db.flush()

    # Restore debt balance (solo capital)
    if debt.debt_type == "mortgage":
        debt.current_balance = refresh_mortgage_current_balance(db, debt, as_of_date=payment.payment_date)
    else:
        debt.current_balance += principal_amount

    # Reactivate debt if it was marked as paid
    if not debt.is_active and debt.current_balance > 0:
        debt.is_active = True

    db.commit()

    return {
        "success": True,
        "message": "Payment deleted and debt balance restored"
    }
