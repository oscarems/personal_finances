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
    update_transaction, delete_transaction
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


class TransactionUpdate(BaseModel):
    account_id: Optional[int] = None
    date: Optional[date] = None
    payee_name: Optional[str] = None
    category_id: Optional[int] = None
    memo: Optional[str] = None
    amount: Optional[float] = None
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
