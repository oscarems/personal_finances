from datetime import datetime, date
import html

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

import web_scrapping_email
from finance_app.database import get_db
from finance_app.models import Account, Currency, Transaction
from finance_app.services.transaction_service import create_transaction

router = APIRouter()

EMAIL_SOURCE = "email_scrape"


class ManualTransactionCreate(BaseModel):
    message_id: str
    account_id: int
    currency_id: int
    category_id: int | None = None
    amount: float
    date: date
    payee_name: str
    memo: str | None = None


@router.get("/messages")
def list_gmail_messages(
    since_date: str | None = Query(default=None, description="Fecha mínima YYYY-MM-DD"),
    max_emails: int = Query(default=50, ge=1, le=300),
    include_non_transactions: bool = Query(default=False, description="Incluir correos no detectados como transacción"),
    db: Session = Depends(get_db),
):
    parsed_since_date = None
    if since_date:
        try:
            parsed_since_date = datetime.strptime(since_date, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="since_date debe estar en formato YYYY-MM-DD") from exc

    try:
        if include_non_transactions:
            rows = web_scrapping_email.fetch_emails_preview(
                since_date=parsed_since_date,
                max_emails=max_emails,
            )
        else:
            rows = web_scrapping_email.fetch_transactions(
                since_date=parsed_since_date,
                max_emails=max_emails,
            )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando Gmail: {exc}") from exc

    message_ids = [row.get("message_id") for row in rows if row.get("message_id")]
    normalized_existing_ids = set()
    if message_ids:
        lookup_ids = set(message_ids)
        lookup_ids.update(html.escape(message_id, quote=True) for message_id in message_ids)

        existing_ids = {
            value for (value,) in db.query(Transaction.source_id)
            .filter(
                Transaction.source == EMAIL_SOURCE,
                Transaction.source_id.in_(lookup_ids)
            )
            .all()
            if value
        }
        normalized_existing_ids = {
            html.unescape(value).strip() for value in existing_ids
        }

    enriched_rows = []
    for row in rows:
        message_id = row.get("message_id")
        normalized_message_id = html.unescape(message_id).strip() if message_id else None
        is_registered = bool(normalized_message_id and normalized_message_id in normalized_existing_ids)
        is_transaction = bool(row.get("is_transaction"))

        row_payload = {
            **row,
            "registered_as_transaction": is_registered,
            "can_create_manual": (not is_registered),
            "status": "registered" if is_registered else ("detected" if is_transaction else "not_detected"),
        }
        enriched_rows.append(row_payload)

    return {
        "total": len(enriched_rows),
        "messages": enriched_rows,
    }


@router.post("/messages/manual-transaction")
def create_manual_gmail_transaction(payload: ManualTransactionCreate, db: Session = Depends(get_db)):
    account = db.query(Account).get(payload.account_id)
    if not account:
        raise HTTPException(status_code=400, detail="Cuenta no encontrada")

    currency = db.query(Currency).get(payload.currency_id)
    if not currency:
        raise HTTPException(status_code=400, detail="Moneda no encontrada")

    existing = db.query(Transaction).filter_by(source=EMAIL_SOURCE, source_id=payload.message_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Este correo ya fue registrado como transacción")

    try:
        tx = create_transaction(db, {
            "account_id": payload.account_id,
            "date": payload.date,
            "payee_name": payload.payee_name,
            "category_id": payload.category_id,
            "memo": payload.memo,
            "amount": payload.amount,
            "currency_id": payload.currency_id,
            "cleared": False,
            "source": EMAIL_SOURCE,
            "source_id": payload.message_id,
        })
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"No se pudo crear la transacción manual: {exc}") from exc

    return {
        "message": "Transacción creada manualmente",
        "transaction": tx.to_dict(),
    }
