"""
Accounts API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from backend.database import get_db
from backend.models import Account, Currency

router = APIRouter()


# Pydantic schemas
class AccountCreate(BaseModel):
    name: str
    type: str  # checking, savings, credit_card, cash
    currency_id: int
    balance: float = 0.0
    is_budget: bool = True


class AccountResponse(BaseModel):
    id: int
    name: str
    type: str
    currency: dict
    balance: float
    is_budget: bool
    is_closed: bool

    class Config:
        from_attributes = True


@router.get("/", response_model=List[AccountResponse])
def get_accounts(db: Session = Depends(get_db)):
    """Get all accounts"""
    accounts = db.query(Account).filter_by(is_closed=False).all()

    return [
        AccountResponse(
            id=acc.id,
            name=acc.name,
            type=acc.type,
            currency=acc.currency.to_dict() if acc.currency else {},
            balance=acc.balance,
            is_budget=acc.is_budget,
            is_closed=acc.is_closed
        )
        for acc in accounts
    ]


@router.post("/", response_model=AccountResponse)
def create_account(account: AccountCreate, db: Session = Depends(get_db)):
    """Create a new account"""
    new_account = Account(
        name=account.name,
        type=account.type,
        currency_id=account.currency_id,
        balance=account.balance,
        is_budget=account.is_budget
    )

    db.add(new_account)
    db.commit()
    db.refresh(new_account)

    return AccountResponse(
        id=new_account.id,
        name=new_account.name,
        type=new_account.type,
        currency=new_account.currency.to_dict() if new_account.currency else {},
        balance=new_account.balance,
        is_budget=new_account.is_budget,
        is_closed=new_account.is_closed
    )


@router.get("/summary")
def get_accounts_summary(db: Session = Depends(get_db)):
    """Get account summary with totals by currency"""
    accounts = db.query(Account).filter_by(is_closed=False).all()

    summary = {
        'accounts': [],
        'total_by_currency': {}
    }

    for account in accounts:
        currency_code = account.currency.code
        if currency_code not in summary['total_by_currency']:
            summary['total_by_currency'][currency_code] = {
                'total': 0,
                'symbol': account.currency.symbol
            }
        summary['total_by_currency'][currency_code]['total'] += account.balance

        summary['accounts'].append({
            'id': account.id,
            'name': account.name,
            'type': account.type,
            'balance': account.balance,
            'currency': account.currency.to_dict()
        })

    return summary
