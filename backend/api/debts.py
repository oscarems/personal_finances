"""
Debts API endpoints - Gestión de deudas
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import date, datetime
import calendar
from dateutil.relativedelta import relativedelta

from backend.database import get_db
from backend.models import Debt, DebtPayment, Account, Transaction

router = APIRouter()


def _adjust_to_payment_day(base_date: date, payment_day: int) -> date:
    if not payment_day:
        return base_date
    last_day = calendar.monthrange(base_date.year, base_date.month)[1]
    safe_day = min(payment_day, last_day)
    return base_date.replace(day=safe_day)


def _build_assumed_payments(debt: Debt, payments: List[DebtPayment]) -> List[dict]:
    if debt.debt_type != "mortgage":
        return []
    if not debt.start_date or not debt.monthly_payment or debt.monthly_payment <= 0:
        return []
    if not payments:
        return []

    first_payment = min(payments, key=lambda payment: payment.payment_date)
    if debt.start_date >= first_payment.payment_date:
        return []

    start_date = _adjust_to_payment_day(debt.start_date, debt.payment_day or 0)
    if start_date < debt.start_date:
        start_date = _adjust_to_payment_day(
            debt.start_date + relativedelta(months=1),
            debt.payment_day or 0
        )

    assumed_dates = []
    current_date = start_date
    while current_date < first_payment.payment_date:
        assumed_dates.append(current_date)
        current_date = current_date + relativedelta(months=1)

    if not assumed_dates:
        return []

    balance_after_first = first_payment.balance_after
    if balance_after_first is None:
        balance_after_first = debt.current_balance

    balance_before_first = max(0.0, balance_after_first + first_payment.amount)
    starting_balance = balance_before_first + debt.monthly_payment * len(assumed_dates)
    balance = starting_balance

    assumed_payments = []
    for assumed_date in assumed_dates:
        balance -= debt.monthly_payment
        assumed_payments.append({
            "id": None,
            "debt_id": debt.id,
            "transaction_id": None,
            "payment_date": assumed_date.isoformat(),
            "amount": debt.monthly_payment,
            "principal": debt.monthly_payment,
            "interest": 0.0,
            "fees": 0.0,
            "balance_after": max(0.0, balance),
            "notes": "Pago asumido (estimado)"
        })

    return assumed_payments


def _build_category_payments(debt: Debt, payments: List[DebtPayment], db: Session) -> List[dict]:
    if not debt.category_id:
        return []

    linked_transaction_ids = {
        payment.transaction_id for payment in payments if payment.transaction_id
    }

    transactions = db.query(Transaction).filter(
        Transaction.category_id == debt.category_id,
        Transaction.amount < 0
    ).order_by(Transaction.date.desc()).all()

    category_payments = []
    for transaction in transactions:
        if transaction.id in linked_transaction_ids:
            continue

        raw_amount = transaction.original_amount if transaction.original_amount is not None else transaction.amount
        amount = abs(raw_amount)
        notes_parts = ["Pago desde presupuesto"]
        if transaction.payee and transaction.payee.name:
            notes_parts.append(transaction.payee.name)
        if transaction.memo:
            notes_parts.append(transaction.memo)

        category_payments.append({
            "id": None,
            "debt_id": debt.id,
            "transaction_id": transaction.id,
            "payment_date": transaction.date.isoformat(),
            "amount": amount,
            "principal": None,
            "interest": None,
            "fees": 0.0,
            "balance_after": None,
            "notes": " · ".join(notes_parts)
        })

    return category_payments


def _calculate_principal_amount(payment: DebtPaymentCreate) -> float:
    if payment.principal is not None:
        return max(0.0, payment.principal)
    interest = payment.interest or 0.0
    fees = payment.fees or 0.0
    principal = payment.amount - interest - fees
    return max(0.0, principal)


# Pydantic Schemas
class DebtCreate(BaseModel):
    """Schema for creating a debt"""
    account_id: int
    name: str
    debt_type: str  # 'credit_card', 'credit_loan', 'mortgage'
    category_id: Optional[int] = None
    currency_code: str = 'COP'
    original_amount: float
    current_balance: float
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

    return [debt.to_dict() for debt in debts]


@router.get("/summary")
def get_debts_summary(db: Session = Depends(get_db)):
    """
    Get summary of all debts grouped by type and currency

    Returns:
        Summary with totals, averages, and statistics
    """
    debts = db.query(Debt).filter(Debt.is_active == True).all()

    summary = {
        'total_debts': len(debts),
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

    if not debts:
        return summary

    total_interest_sum = 0
    interest_count = 0

    for debt in debts:
        debt_dict = debt.to_dict()

        # Group by type
        if debt.debt_type not in summary['by_type']:
            summary['by_type'][debt.debt_type] = {
                'count': 0,
                'total_balance': 0,
                'total_original': 0
            }
        summary['by_type'][debt.debt_type]['count'] += 1
        summary['by_type'][debt.debt_type]['total_balance'] += debt.current_balance
        summary['by_type'][debt.debt_type]['total_original'] += debt.original_amount

        # Group by currency
        if debt.currency_code not in summary['by_currency']:
            summary['by_currency'][debt.currency_code] = {
                'count': 0,
                'total_balance': 0
            }
        summary['by_currency'][debt.currency_code]['count'] += 1
        summary['by_currency'][debt.currency_code]['total_balance'] += debt.current_balance

        # Totals by currency
        if debt.currency_code not in summary['total_original']:
            summary['total_original'][debt.currency_code] = 0
            summary['total_current'][debt.currency_code] = 0
            summary['total_paid'][debt.currency_code] = 0
            summary['total_monthly_payment'][debt.currency_code] = 0

        summary['total_original'][debt.currency_code] += debt.original_amount
        summary['total_current'][debt.currency_code] += debt.current_balance
        summary['total_paid'][debt.currency_code] += (debt.original_amount - debt.current_balance)

        if debt.monthly_payment:
            summary['total_monthly_payment'][debt.currency_code] += debt.monthly_payment

        # Average interest rate
        if debt.interest_rate:
            total_interest_sum += debt.interest_rate
            interest_count += 1

        # Debts near payoff
        if debt_dict['paid_percentage'] >= 90:
            summary['debts_near_payoff'].append({
                'id': debt.id,
                'name': debt.name,
                'remaining': debt.current_balance,
                'percentage': debt_dict['paid_percentage']
            })

        # High interest debts
        if debt.interest_rate and debt.interest_rate > 20:
            summary['high_interest_debts'].append({
                'id': debt.id,
                'name': debt.name,
                'interest_rate': debt.interest_rate,
                'balance': debt.current_balance
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

    return debt.to_dict(include_payments=include_payments)


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
    new_debt = Debt(
        account_id=debt_data.account_id,
        name=debt_data.name,
        debt_type=debt_data.debt_type,
        category_id=debt_data.category_id,
        currency_code=debt_data.currency_code,
        original_amount=debt_data.original_amount,
        current_balance=debt_data.current_balance,
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

    return debt.to_dict()


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

    payments = db.query(DebtPayment).filter_by(debt_id=debt_id).order_by(
        DebtPayment.payment_date.desc()
    ).all()

    assumed_payments = _build_assumed_payments(debt, payments)
    category_payments = _build_category_payments(debt, payments, db)
    payment_dicts = [payment.to_dict() for payment in payments]
    all_payments = payment_dicts + assumed_payments + category_payments

    if not all_payments:
        return []

    return sorted(
        all_payments,
        key=lambda payment: date.fromisoformat(payment["payment_date"]),
        reverse=True
    )


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

    # Update debt balance
    debt.current_balance = balance_after

    # If debt is fully paid, mark as inactive
    if balance_after <= 0:
        debt.is_active = False

    db.add(new_payment)
    db.commit()
    db.refresh(new_payment)
    db.refresh(debt)

    return {
        "payment": new_payment.to_dict(),
        "debt": debt.to_dict()
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

    # Restore debt balance (solo capital)
    debt.current_balance += principal_amount

    # Reactivate debt if it was marked as paid
    if not debt.is_active and debt.current_balance > 0:
        debt.is_active = True

    db.delete(payment)
    db.commit()

    return {
        "success": True,
        "message": "Payment deleted and debt balance restored"
    }
