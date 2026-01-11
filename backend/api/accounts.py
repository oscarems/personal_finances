"""
Accounts API endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from backend.database import get_db
from backend.models import Account
from backend.services.transaction_service import get_account_summary

router = APIRouter()


@router.get("/")
def list_accounts(db: Session = Depends(get_db)):
    """Get all accounts"""
    accounts = db.query(Account).filter_by(is_closed=False).all()
    return [acc.to_dict() for acc in accounts]


@router.get("/summary")
def account_summary(db: Session = Depends(get_db)):
    """Get account summary with balances"""
    return get_account_summary(db)
