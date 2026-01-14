"""
Accounts API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import date

from backend.database import get_db
from backend.models import Account, Currency
from backend.services.transaction_service import get_account_summary

router = APIRouter()


# Pydantic schemas
class AccountCreate(BaseModel):
    name: str
    type: str  # checking, savings, credit_card, credit_loan, mortgage, cdt, investment, cash
    currency_id: int
    balance: float = 0.0
    is_budget: bool = True
    notes: Optional[str] = None
    # Optional fields based on account type
    interest_rate: Optional[float] = None
    credit_limit: Optional[float] = None
    monthly_payment: Optional[float] = None
    original_amount: Optional[float] = None
    payment_due_day: Optional[int] = None
    maturity_date: Optional[date] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    notes: Optional[str] = None
    is_budget: Optional[bool] = None
    # Optional fields based on account type
    interest_rate: Optional[float] = None
    credit_limit: Optional[float] = None
    monthly_payment: Optional[float] = None
    original_amount: Optional[float] = None
    payment_due_day: Optional[int] = None
    maturity_date: Optional[date] = None


@router.get("/")
def list_accounts(db: Session = Depends(get_db)):
    """Get all accounts"""
    accounts = db.query(Account).filter_by(is_closed=False).all()
    return [acc.to_dict() for acc in accounts]


@router.get("/summary")
def account_summary(db: Session = Depends(get_db)):
    """Get account summary with balances"""
    return get_account_summary(db)


@router.get("/{account_id}")
def get_account(account_id: int, db: Session = Depends(get_db)):
    """Get single account"""
    account = db.query(Account).get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account.to_dict()


@router.post("/")
def create_account(account_data: AccountCreate, db: Session = Depends(get_db)):
    """Create new account"""
    # Verify currency exists
    currency = db.query(Currency).get(account_data.currency_id)
    if not currency:
        raise HTTPException(status_code=400, detail="Currency not found")

    # Create account
    account = Account(
        name=account_data.name,
        type=account_data.type,
        currency_id=account_data.currency_id,
        balance=account_data.balance,
        is_budget=account_data.is_budget,
        notes=account_data.notes,
        interest_rate=account_data.interest_rate,
        credit_limit=account_data.credit_limit,
        monthly_payment=account_data.monthly_payment,
        original_amount=account_data.original_amount,
        payment_due_day=account_data.payment_due_day,
        maturity_date=account_data.maturity_date
    )

    db.add(account)
    db.commit()
    db.refresh(account)

    return account.to_dict()


@router.put("/{account_id}")
def update_account(account_id: int, account_data: AccountUpdate, db: Session = Depends(get_db)):
    """Update account"""
    account = db.query(Account).get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Update only provided fields
    if account_data.name is not None:
        account.name = account_data.name
    if account_data.type is not None:
        account.type = account_data.type
    if account_data.notes is not None:
        account.notes = account_data.notes
    if account_data.is_budget is not None:
        account.is_budget = account_data.is_budget

    # Update optional fields
    if account_data.interest_rate is not None:
        account.interest_rate = account_data.interest_rate
    if account_data.credit_limit is not None:
        account.credit_limit = account_data.credit_limit
    if account_data.monthly_payment is not None:
        account.monthly_payment = account_data.monthly_payment
    if account_data.original_amount is not None:
        account.original_amount = account_data.original_amount
    if account_data.payment_due_day is not None:
        account.payment_due_day = account_data.payment_due_day
    if account_data.maturity_date is not None:
        account.maturity_date = account_data.maturity_date

    db.commit()
    db.refresh(account)

    return account.to_dict()


@router.delete("/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    """Close account (soft delete)"""
    account = db.query(Account).get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    account.is_closed = True
    db.commit()

    return {"success": True, "message": "Account closed"}
