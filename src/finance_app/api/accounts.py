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
from finance_app.services.debt.balance_service import calculate_scheduled_principal_balance
from finance_app.services.mortgage.service import resolve_effective_monthly_payment, calculate_monthly_payment

router = APIRouter()


# Pydantic schemas
class AccountCreate(BaseModel):
    name: str
    type: str  # checking, savings, credit_card, credit_loan, mortgage, cdt, investment, cash
    currency_id: int
    balance: float = 0.0
    is_budget: bool = True
    country: Optional[str] = None
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
    actual_payment_amount: Optional[float] = None
    has_insurance: Optional[bool] = None
    includes_principal_payment: Optional[bool] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    country: Optional[str] = None
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
    actual_payment_amount: Optional[float] = None
    has_insurance: Optional[bool] = None
    includes_principal_payment: Optional[bool] = None


@router.get("")
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

        # Include linked debt summary for UI display
        if linked_debt:
            account_data["linked_debt"] = {
                "id": linked_debt.id,
                "name": linked_debt.name,
                "debt_type": linked_debt.debt_type,
                "interest_rate": linked_debt.interest_rate,
                "monthly_payment": linked_debt.monthly_payment,
                "original_amount": linked_debt.original_amount,
                "current_balance": linked_debt.current_balance,
                "institution": linked_debt.institution,
            }
        else:
            account_data["linked_debt"] = None

        serialized_accounts.append(account_data)

    return serialized_accounts


@router.get("/summary")
def account_summary(db: Session = Depends(get_db)):
    """Get account summary with balances"""
    return get_account_summary(db)


@router.get("/{account_id}")
def get_account(account_id: int, db: Session = Depends(get_db)):
    """Get single account"""
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account.to_dict()


@router.post("")
@router.post("/")
def create_account(account_data: AccountCreate, db: Session = Depends(get_db)):
    """Create new account"""
    # Verify currency exists
    currency = db.get(Currency, account_data.currency_id)
    if not currency:
        raise HTTPException(status_code=400, detail="Currency not found")

    # Create account
    account = Account(
        name=account_data.name,
        type=account_data.type,
        currency_id=account_data.currency_id,
        balance=account_data.balance,
        is_budget=account_data.is_budget,
        country=account_data.country,
        notes=account_data.notes,
        interest_rate=account_data.interest_rate,
        credit_limit=account_data.credit_limit,
        monthly_payment=account_data.monthly_payment,
        original_amount=account_data.original_amount,
        loan_years=account_data.loan_years,
        loan_start_date=account_data.loan_start_date,
        payment_due_day=account_data.payment_due_day,
        maturity_date=account_data.maturity_date,
        actual_payment_amount=account_data.actual_payment_amount,
        has_insurance=account_data.has_insurance or False,
        includes_principal_payment=account_data.includes_principal_payment or False,
    )

    db.add(account)
    db.commit()
    db.refresh(account)

    if account.type in {'credit_card', 'credit_loan', 'mortgage'}:
        from finance_app.models import Debt

        existing_debt = db.query(Debt).filter_by(account_id=account.id).first()
        if not existing_debt:
            original_amount = account.original_amount or abs(account.balance or 0.0)
            start_date = account.loan_start_date or date.today()

            if account.type == "mortgage":
                # Mortgages are fully derived from original_amount/start_date/rate/term —
                # actual_payment_amount / includes_principal_payment do not apply.
                if not original_amount or account.interest_rate is None or not account.loan_years:
                    raise HTTPException(
                        status_code=400,
                        detail="Una hipoteca requiere monto inicial, tasa de interés y plazo (años)."
                    )
                engine_payment = calculate_monthly_payment(
                    original_amount, account.interest_rate / 100, account.loan_years
                )
                debt = Debt(
                    account_id=account.id,
                    name=account.name,
                    debt_type=account.type,
                    currency_code=account.currency.code,
                    original_amount=original_amount,
                    current_balance=original_amount,  # placeholder, recalculated below
                    interest_rate=account.interest_rate,
                    annual_interest_rate=account.interest_rate,
                    monthly_payment=engine_payment,
                    loan_years=account.loan_years,
                    term_months=account.loan_years * 12,
                    start_date=start_date,
                    has_insurance=account.has_insurance or False,
                )
            else:
                current_balance = abs(account.balance or 0.0)
                payment_info = resolve_effective_monthly_payment(
                    original_amount=original_amount,
                    annual_rate_pct=account.interest_rate,
                    loan_years=account.loan_years,
                    actual_payment_amount=account.actual_payment_amount,
                    includes_principal_payment=account.includes_principal_payment,
                )
                engine_payment = payment_info['engine_payment'] or account.monthly_payment

                debt = Debt(
                    account_id=account.id,
                    name=account.name,
                    debt_type=account.type,
                    currency_code=account.currency.code,
                    original_amount=original_amount,
                    current_balance=current_balance,
                    credit_limit=account.credit_limit,
                    interest_rate=account.interest_rate,
                    monthly_payment=engine_payment,
                    loan_years=account.loan_years,
                    start_date=start_date,
                    has_insurance=account.has_insurance or False,
                    includes_principal_payment=account.includes_principal_payment or False,
                    actual_payment_amount=account.actual_payment_amount,
                )
            db.add(debt)
            db.commit()

            if account.type == "mortgage":
                db.refresh(debt)
                debt.current_balance = calculate_scheduled_principal_balance(debt, date.today())
                account.monthly_payment = debt.monthly_payment
                account.balance = -abs(debt.current_balance or 0.0)
                db.commit()

    return account.to_dict()


@router.put("/{account_id}")
def update_account(account_id: int, account_data: AccountUpdate, db: Session = Depends(get_db)):
    """Update account"""
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Update only provided fields
    if account_data.name is not None:
        account.name = account_data.name
    if account_data.type is not None:
        account.type = account_data.type
    if account_data.country is not None:
        account.country = account_data.country
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
    if account_data.actual_payment_amount is not None:
        account.actual_payment_amount = account_data.actual_payment_amount
    if account_data.has_insurance is not None:
        account.has_insurance = account_data.has_insurance
    if account_data.includes_principal_payment is not None:
        account.includes_principal_payment = account_data.includes_principal_payment

    db.commit()
    db.refresh(account)

    # Sync relevant fields to the linked Debt record if it exists
    linked_debt = db.query(Debt).filter_by(account_id=account_id).first()
    if linked_debt:
        if account_data.name is not None:
            linked_debt.name = account_data.name
        if account_data.interest_rate is not None:
            linked_debt.interest_rate = account_data.interest_rate
        if account_data.credit_limit is not None:
            linked_debt.credit_limit = account_data.credit_limit
        if account_data.original_amount is not None:
            linked_debt.original_amount = account_data.original_amount
        if account_data.loan_years is not None:
            linked_debt.loan_years = account_data.loan_years
        if account_data.loan_start_date is not None:
            linked_debt.start_date = account_data.loan_start_date
        if account_data.has_insurance is not None:
            linked_debt.has_insurance = account_data.has_insurance

        if linked_debt.debt_type == "mortgage":
            # Mortgages are fully derived from original_amount/start_date/rate/term —
            # actual_payment_amount/includes_principal_payment and manual monthly_payment
            # overrides no longer apply.
            linked_debt.annual_interest_rate = linked_debt.interest_rate
            if linked_debt.loan_years:
                linked_debt.term_months = linked_debt.loan_years * 12
            if linked_debt.original_amount and linked_debt.interest_rate is not None and linked_debt.loan_years:
                linked_debt.monthly_payment = calculate_monthly_payment(
                    linked_debt.original_amount, linked_debt.interest_rate / 100, linked_debt.loan_years
                )
            linked_debt.current_balance = calculate_scheduled_principal_balance(linked_debt, date.today())
            account.monthly_payment = linked_debt.monthly_payment
            account.balance = -abs(linked_debt.current_balance or 0.0)
        else:
            if account_data.includes_principal_payment is not None:
                linked_debt.includes_principal_payment = account_data.includes_principal_payment
            if account_data.actual_payment_amount is not None:
                linked_debt.actual_payment_amount = account_data.actual_payment_amount

            # Recompute the effective payment fed to the amortization engine whenever
            # any of its inputs changed, so the schedule stays consistent.
            recompute_triggers = (
                account_data.interest_rate, account_data.original_amount, account_data.loan_years,
                account_data.actual_payment_amount, account_data.includes_principal_payment,
                account_data.monthly_payment,
            )
            if any(v is not None for v in recompute_triggers):
                if account_data.monthly_payment is not None and not linked_debt.includes_principal_payment:
                    # Explicit manual override of the base payment (no actual/extra tracking in play).
                    linked_debt.monthly_payment = account_data.monthly_payment
                else:
                    payment_info = resolve_effective_monthly_payment(
                        original_amount=linked_debt.original_amount,
                        annual_rate_pct=linked_debt.interest_rate,
                        loan_years=linked_debt.loan_years,
                        actual_payment_amount=linked_debt.actual_payment_amount,
                        includes_principal_payment=linked_debt.includes_principal_payment,
                    )
                    if payment_info['engine_payment']:
                        linked_debt.monthly_payment = payment_info['engine_payment']
                    elif account_data.monthly_payment is not None:
                        linked_debt.monthly_payment = account_data.monthly_payment
            elif account_data.monthly_payment is not None:
                linked_debt.monthly_payment = account_data.monthly_payment

        db.commit()

    return account.to_dict()


class AccountAdjust(BaseModel):
    new_balance: float
    note: Optional[str] = None


@router.post("/{account_id}/adjust")
def adjust_account_balance(account_id: int, data: AccountAdjust, db: Session = Depends(get_db)):
    """Adjust account balance to match real statement balance"""
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if account.type == "mortgage":
        raise HTTPException(
            status_code=400,
            detail="El saldo de una hipoteca se deriva del monto inicial, tasa, "
                    "plazo y fecha de inicio — no se puede ajustar manualmente."
        )

    account.balance = data.new_balance
    db.commit()
    db.refresh(account)

    return account.to_dict()


@router.delete("/{account_id}")
def delete_account(account_id: int, db: Session = Depends(get_db)):
    """Close account (soft delete)"""
    account = db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    account.is_closed = True
    db.commit()

    return {"success": True, "message": "Account closed"}
