"""
Reconciliation API endpoints
"""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from backend.database import get_db
from backend.models import ReconciliationSession
from backend.services.reconciliation_service import (
    get_reconciliation_summary,
    mark_transactions_cleared,
    create_reconciliation_session
)

router = APIRouter()


class MarkClearedRequest(BaseModel):
    transaction_ids: List[int]
    cleared: bool = True


class ReconciliationCreate(BaseModel):
    account_id: int
    statement_date: date
    statement_balance: float
    notes: Optional[str] = None
    create_adjustment_entry: bool = False


@router.get("/summary")
def reconciliation_summary(
    account_id: int,
    statement_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    try:
        return get_reconciliation_summary(db, account_id, statement_date)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/mark-cleared")
def reconcile_mark_cleared(request: MarkClearedRequest, db: Session = Depends(get_db)):
    updated = mark_transactions_cleared(db, request.transaction_ids, request.cleared)
    return {"updated": updated}


@router.post("/sessions")
def create_session(request: ReconciliationCreate, db: Session = Depends(get_db)):
    session = create_reconciliation_session(
        db,
        account_id=request.account_id,
        statement_date=request.statement_date,
        statement_balance=request.statement_balance,
        notes=request.notes,
        create_adjustment_entry=request.create_adjustment_entry
    )
    return session.to_dict()


@router.get("/sessions/{account_id}")
def list_sessions(account_id: int, db: Session = Depends(get_db)):
    sessions = db.query(ReconciliationSession).filter_by(account_id=account_id).order_by(
        ReconciliationSession.statement_date.desc(),
        ReconciliationSession.id.desc()
    ).all()
    return [session.to_dict() for session in sessions]
