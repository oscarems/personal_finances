"""
Accounts API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import date

from finance_app.database import get_db
from finance_app.models import Account, Currency, Debt
from finance_app.services.transaction_service import get_account_summary
from finance_app.services.debt_balance_service import calculate_scheduled_principal_balance

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
    loan_years: Optional[int] = None
    loan_start_date: Optional[date] = None
    payment_due_day: Optional[int] = None
    maturity_date: Optional[date] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    notes: Optional[str] = None
    is_budget: Optional[bool] = None
    balance: Optional[float] = None
    # Optional fields based on account type
    interest_rate: Optional[float] = None
    credit_limit: Optional[float] = None
    monthly_payment: Optional[float] = None
    original_amount: Optional[float] = None
    loan_years: Optional[int] = None
    loan_start_date: Optional[date] = None
    payment_due_day: Optional[int] = None
    maturity_date: Optional[date] = None


@router.get("/")
def list_accounts(type: Optional[str] = None, db: Session = Depends(get_db)):
    """Get all accounts"""
    query = db.query(Account).filter_by(is_closed=False)
    if type:
        query = query.filter(Account.type == type)
    accounts = query.all()

    debt_by_account_id = {
        debt.account_id: debt
        for debt in db.query(Debt).filter(Debt.account_id.in_([acc.id for acc in accounts])).all()
    } if accounts else {}

    serialized_accounts = []
    for account in accounts:
        account_data = account.to_dict()
        linked_debt = debt_by_account_id.get(account.id)

        if linked_debt and account.type in {"credit_card", "credit_loan", "mortgage"}:
            if account.type == "credit_card":
                debt_balance = max(0.0, -(account.balance or 0.0))
            else:
                debt_balance = calculate_scheduled_principal_balance(
                    debt=linked_debt,
                    as_of_date=date.today(),
                )

            # La UI de cuentas muestra deudas como números rojos con valor absoluto,
            # por eso mantenemos el signo negativo para representar obligación.
            account_data["balance"] = -float(debt_balance)

        serialized_accounts.append(account_data)

    return serialized_accounts


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
        loan_years=account_data.loan_years,
        loan_start_date=account_data.loan_start_date,
        payment_due_day=account_data.payment_due_day,
        maturity_date=account_data.maturity_date
    )

    db.add(account)
    db.commit()
    db.refresh(account)

    if account.type in {'credit_card', 'credit_loan', 'mortgage'}:
        from finance_app.models import Debt

        existing_debt = db.query(Debt).filter_by(account_id=account.id).first()
        if not existing_debt:
            current_balance = abs(account.balance or 0.0)
            original_amount = account.original_amount or current_balance

            debt = Debt(
                account_id=account.id,
                name=account.name,
                debt_type=account.type,
                currency_code=account.currency.code,
                original_amount=original_amount,
                current_balance=current_balance,
                credit_limit=account.credit_limit,
                interest_rate=account.interest_rate,
                monthly_payment=account.monthly_payment,
                loan_years=account.loan_years,
                start_date=account.loan_start_date or date.today()
            )
            db.add(debt)
            db.commit()

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
    if account_data.balance is not None:
        account.balance = account_data.balance

    # Update optional fields
    if account_data.interest_rate is not None:
        account.interest_rate = account_data.interest_rate
    if account_data.credit_limit is not None:
        account.credit_limit = account_data.credit_limit
    if account_data.monthly_payment is not None:
        account.monthly_payment = account_data.monthly_payment
    if account_data.original_amount is not None:
        account.original_amount = account_data.original_amount
    if account_data.loan_years is not None:
        account.loan_years = account_data.loan_years
    if account_data.loan_start_date is not None:
        account.loan_start_date = account_data.loan_start_date
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
