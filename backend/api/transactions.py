"""
Transactions API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime
from pydantic import BaseModel

from backend.database import get_db
from backend.models import Transaction, Account, Category, Payee, Currency

router = APIRouter()


# Pydantic schemas
class TransactionCreate(BaseModel):
    account_id: int
    date: date
    payee_name: Optional[str] = None
    category_id: Optional[int] = None
    memo: Optional[str] = ""
    amount: float
    currency_id: int
    cleared: bool = False


class TransactionResponse(BaseModel):
    id: int
    account_id: int
    account_name: str
    date: date
    payee_name: Optional[str]
    category_id: Optional[int]
    category_name: Optional[str]
    memo: Optional[str]
    amount: float
    currency: dict
    cleared: bool

    class Config:
        from_attributes = True


@router.get("/", response_model=List[TransactionResponse])
def get_transactions(
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get transactions with optional filters"""
    query = db.query(Transaction)

    if account_id:
        query = query.filter(Transaction.account_id == account_id)

    if category_id:
        query = query.filter(Transaction.category_id == category_id)

    transactions = query.order_by(Transaction.date.desc()).limit(limit).all()

    return [
        TransactionResponse(
            id=t.id,
            account_id=t.account_id,
            account_name=t.account.name if t.account else "",
            date=t.date,
            payee_name=t.payee.name if t.payee else None,
            category_id=t.category_id,
            category_name=t.category.name if t.category else None,
            memo=t.memo,
            amount=t.amount,
            currency=t.currency.to_dict() if t.currency else {},
            cleared=t.cleared
        )
        for t in transactions
    ]


@router.post("/", response_model=TransactionResponse)
def create_transaction(transaction: TransactionCreate, db: Session = Depends(get_db)):
    """Create a new transaction"""
    # Get or create payee
    payee = None
    if transaction.payee_name:
        payee = db.query(Payee).filter_by(name=transaction.payee_name).first()
        if not payee:
            payee = Payee(name=transaction.payee_name)
            db.add(payee)
            db.flush()

    # Create transaction
    new_transaction = Transaction(
        account_id=transaction.account_id,
        date=transaction.date,
        payee_id=payee.id if payee else None,
        category_id=transaction.category_id,
        memo=transaction.memo,
        amount=transaction.amount,
        currency_id=transaction.currency_id,
        cleared=transaction.cleared
    )

    db.add(new_transaction)

    # Update account balance
    account = db.query(Account).get(transaction.account_id)
    if account:
        account.balance += transaction.amount

    db.commit()
    db.refresh(new_transaction)

    return TransactionResponse(
        id=new_transaction.id,
        account_id=new_transaction.account_id,
        account_name=new_transaction.account.name if new_transaction.account else "",
        date=new_transaction.date,
        payee_name=new_transaction.payee.name if new_transaction.payee else None,
        category_id=new_transaction.category_id,
        category_name=new_transaction.category.name if new_transaction.category else None,
        memo=new_transaction.memo,
        amount=new_transaction.amount,
        currency=new_transaction.currency.to_dict() if new_transaction.currency else {},
        cleared=new_transaction.cleared
    )


@router.delete("/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """Delete a transaction"""
    transaction = db.query(Transaction).get(transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Update account balance
    account = db.query(Account).get(transaction.account_id)
    if account:
        account.balance -= transaction.amount

    db.delete(transaction)
    db.commit()

    return {"message": "Transaction deleted successfully"}
