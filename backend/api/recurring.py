"""
Recurring Transactions API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import date

from backend.database import get_db
from backend.models import RecurringTransaction, Payee
from backend.services.recurring_service import (
    generate_due_transactions,
    preview_next_occurrences
)

router = APIRouter()


# Pydantic schemas
class RecurringTransactionCreate(BaseModel):
    account_id: int
    payee_name: Optional[str] = None
    category_id: Optional[int] = None
    description: str
    amount: float
    transaction_type: str = 'expense'  # expense or income
    currency_id: int
    frequency: str  # daily, weekly, monthly, yearly
    interval: int = 1
    start_date: date
    end_date: Optional[date] = None
    day_of_week: Optional[int] = None  # 0-6 for weekly
    day_of_month: Optional[int] = None  # 1-31 for monthly


class RecurringTransactionUpdate(BaseModel):
    account_id: Optional[int] = None
    payee_name: Optional[str] = None
    category_id: Optional[int] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    transaction_type: Optional[str] = None
    frequency: Optional[str] = None
    interval: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    is_active: Optional[bool] = None


@router.get("/")
def list_recurring_transactions(
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """Get all recurring transactions"""
    query = db.query(RecurringTransaction)

    if is_active is not None:
        query = query.filter(RecurringTransaction.is_active == is_active)

    recurring_txs = query.all()
    return [rt.to_dict() for rt in recurring_txs]


@router.get("/{recurring_id}")
def get_recurring_transaction(recurring_id: int, db: Session = Depends(get_db)):
    """Get single recurring transaction"""
    recurring = db.query(RecurringTransaction).get(recurring_id)
    if not recurring:
        raise HTTPException(status_code=404, detail="Recurring transaction not found")
    return recurring.to_dict()


@router.post("/")
def create_recurring_transaction(
    data: RecurringTransactionCreate,
    db: Session = Depends(get_db)
):
    """Create new recurring transaction"""
    # Get or create payee
    payee_id = None
    if data.payee_name:
        payee = db.query(Payee).filter_by(name=data.payee_name).first()
        if not payee:
            payee = Payee(name=data.payee_name)
            db.add(payee)
            db.flush()
        payee_id = payee.id

    # Create recurring transaction
    recurring = RecurringTransaction(
        account_id=data.account_id,
        payee_id=payee_id,
        category_id=data.category_id,
        description=data.description,
        amount=data.amount,
        transaction_type=data.transaction_type,
        currency_id=data.currency_id,
        frequency=data.frequency,
        interval=data.interval,
        start_date=data.start_date,
        end_date=data.end_date,
        day_of_week=data.day_of_week,
        day_of_month=data.day_of_month,
        is_active=True
    )

    db.add(recurring)
    db.commit()
    db.refresh(recurring)

    return recurring.to_dict()


@router.put("/{recurring_id}")
def update_recurring_transaction(
    recurring_id: int,
    data: RecurringTransactionUpdate,
    db: Session = Depends(get_db)
):
    """Update recurring transaction"""
    recurring = db.query(RecurringTransaction).get(recurring_id)
    if not recurring:
        raise HTTPException(status_code=404, detail="Recurring transaction not found")

    # Update payee if needed
    if data.payee_name is not None:
        payee = db.query(Payee).filter_by(name=data.payee_name).first()
        if not payee:
            payee = Payee(name=data.payee_name)
            db.add(payee)
            db.flush()
        recurring.payee_id = payee.id

    # Update fields
    update_fields = {
        'account_id', 'category_id', 'description', 'amount', 'transaction_type',
        'frequency', 'interval', 'start_date', 'end_date',
        'day_of_week', 'day_of_month', 'is_active'
    }

    for field in update_fields:
        value = getattr(data, field)
        if value is not None:
            setattr(recurring, field, value)

    db.commit()
    db.refresh(recurring)

    return recurring.to_dict()


@router.delete("/{recurring_id}")
def delete_recurring_transaction(recurring_id: int, db: Session = Depends(get_db)):
    """Delete recurring transaction"""
    recurring = db.query(RecurringTransaction).get(recurring_id)
    if not recurring:
        raise HTTPException(status_code=404, detail="Recurring transaction not found")

    db.delete(recurring)
    db.commit()

    return {"success": True, "message": "Recurring transaction deleted"}


@router.post("/{recurring_id}/toggle")
def toggle_recurring_transaction(recurring_id: int, db: Session = Depends(get_db)):
    """Toggle active status of recurring transaction"""
    recurring = db.query(RecurringTransaction).get(recurring_id)
    if not recurring:
        raise HTTPException(status_code=404, detail="Recurring transaction not found")

    recurring.is_active = not recurring.is_active
    db.commit()

    return {
        "success": True,
        "is_active": recurring.is_active,
        "message": f"Recurring transaction {'activated' if recurring.is_active else 'deactivated'}"
    }


@router.get("/{recurring_id}/preview")
def preview_recurring_transaction(
    recurring_id: int,
    count: int = 5,
    db: Session = Depends(get_db)
):
    """Preview next N occurrences of recurring transaction"""
    recurring = db.query(RecurringTransaction).get(recurring_id)
    if not recurring:
        raise HTTPException(status_code=404, detail="Recurring transaction not found")

    next_dates = preview_next_occurrences(recurring, count)

    return {
        "recurring_id": recurring_id,
        "description": recurring.description,
        "amount": recurring.amount,
        "next_occurrences": [d.isoformat() for d in next_dates]
    }


@router.post("/generate")
def generate_recurring_transactions(
    up_to_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Generate all due recurring transactions
    This should be run daily (e.g., via cron job)
    """
    if up_to_date:
        target_date = date.fromisoformat(up_to_date)
    else:
        target_date = date.today()

    stats = generate_due_transactions(db, target_date)

    return {
        "success": True,
        "stats": stats,
        "message": f"Generated {stats['generated']} transactions"
    }
