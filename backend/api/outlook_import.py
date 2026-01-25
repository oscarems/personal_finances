"""
Microsoft Outlook email import endpoints.
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.microsoft_graph_service import (
    fetch_bank_messages,
    poll_device_flow,
    start_device_flow,
)
from backend.services.transaction_service import create_transaction

router = APIRouter()


class OutlookTransaction(BaseModel):
    account_id: int
    date: date
    payee_name: Optional[str] = None
    category_id: Optional[int] = None
    memo: Optional[str] = None
    amount: float
    currency_id: int
    cleared: bool = False


class OutlookImportPayload(BaseModel):
    transactions: List[OutlookTransaction] = Field(default_factory=list)


@router.post("/device-code")
def outlook_device_code():
    """Start device code authentication flow for Microsoft Graph."""
    try:
        flow = start_device_flow()
        return {
            "user_code": flow.get("user_code"),
            "verification_uri": flow.get("verification_uri"),
            "expires_in": flow.get("expires_in"),
            "interval": flow.get("interval"),
            "message": flow.get("message"),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/token")
def outlook_poll_token():
    """Poll for device code authorization status."""
    try:
        return poll_device_flow()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/transactions")
def outlook_fetch_transactions(
    domain: str,
    days: int = 30,
    limit: int = 50,
):
    """Fetch bank emails and return parsed transactions."""
    if not domain:
        raise HTTPException(status_code=400, detail="Debes indicar el dominio del banco.")
    try:
        return fetch_bank_messages(domain=domain, days=days, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al consultar Outlook: {exc}") from exc


@router.post("/transactions")
def outlook_import_transactions(payload: OutlookImportPayload, db: Session = Depends(get_db)):
    """Create transactions from approved Outlook messages."""
    if not payload.transactions:
        raise HTTPException(status_code=400, detail="No hay transacciones para importar.")

    created = []
    for item in payload.transactions:
        transaction = create_transaction(db, item.dict())
        created.append(transaction.to_dict())
    return {"success": True, "count": len(created), "transactions": created}
