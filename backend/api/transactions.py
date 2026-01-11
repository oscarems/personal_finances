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


@router.post("/")
def create_new_transaction(transaction: TransactionCreate, db: Session = Depends(get_db)):
    """Create a new transaction"""
    data = transaction.dict()
    new_transaction = create_transaction(db, data)
    return new_transaction.to_dict()


@router.delete("/{transaction_id}")
def remove_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """Delete a transaction"""
    success = delete_transaction(db, transaction_id)
    if not success:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"success": True}
