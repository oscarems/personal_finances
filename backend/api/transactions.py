"""
Transactions API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import date

from backend.database import get_db
from backend.services.transaction_service import (
    create_transaction, get_transactions, get_transaction_by_id,
    update_transaction, delete_transaction, create_transfer
)

router = APIRouter()


# Pydantic schemas
class TransactionCreate(BaseModel):
    account_id: int
    date: date
    payee_name: Optional[str] = None
    category_id: Optional[int] = None
    memo: Optional[str] = None
    amount: float
    currency_id: int
    cleared: bool = False


class TransferCreate(BaseModel):
    from_account_id: int
    to_account_id: int
    date: date
    amount: float
    from_currency_id: int
    to_currency_id: int
    memo: Optional[str] = None
    cleared: bool = False


class TransactionUpdate(BaseModel):
    account_id: Optional[int] = None
    date: Optional[date] = None
    payee_name: Optional[str] = None
    category_id: Optional[int] = None
    memo: Optional[str] = None
    amount: Optional[float] = None
    currency_id: Optional[int] = None
    cleared: Optional[bool] = None


@router.get("/")
def list_transactions(
    account_id: Optional[int] = None,
    category_id: Optional[int] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get list of transactions"""
    transactions = get_transactions(db, account_id=account_id, category_id=category_id, limit=limit)
    return [t.to_dict() for t in transactions]


@router.get("/{transaction_id}")
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """Get single transaction"""
    transaction = get_transaction_by_id(db, transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction.to_dict()


@router.post("/")
def create_new_transaction(transaction: TransactionCreate, db: Session = Depends(get_db)):
    """Create a new transaction"""
    data = transaction.dict()
    new_transaction = create_transaction(db, data)
    return new_transaction.to_dict()


@router.put("/{transaction_id}")
def update_existing_transaction(
    transaction_id: int,
    transaction: TransactionUpdate,
    db: Session = Depends(get_db)
):
    """Update an existing transaction"""
    data = {k: v for k, v in transaction.dict().items() if v is not None}
    updated_transaction = update_transaction(db, transaction_id, data)
    if not updated_transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return updated_transaction.to_dict()


@router.delete("/{transaction_id}")
def remove_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """Delete a transaction"""
    success = delete_transaction(db, transaction_id)
    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"success": True}


@router.post("/transfer")
def create_account_transfer(transfer: TransferCreate, db: Session = Depends(get_db)):
    """
    Create a transfer between two accounts.
    This creates two linked transactions (outflow from source, inflow to destination).
    Supports transfers between different currencies.
    """
    if transfer.from_account_id == transfer.to_account_id:
        raise HTTPException(status_code=400, detail="Cannot transfer to the same account")

    if transfer.amount <= 0:
        raise HTTPException(status_code=400, detail="Transfer amount must be positive")

    transactions = create_transfer(db, transfer.dict())
    return {
        "success": True,
        "from_transaction": transactions[0].to_dict(),
        "to_transaction": transactions[1].to_dict()
    }
