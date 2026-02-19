from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

import web_scrapping_email
from finance_app.config import get_settings
from finance_app.database import get_db
from finance_app.models import Currency, EmailScrapeTransaction, Transaction
from finance_app.services.transaction_service import create_transaction
from finance_app.sync.email_scrape_sync import EMAIL_SOURCE, _resolve_account

router = APIRouter()


class ManualGmailImportPayload(BaseModel):
    message_id: str
    fecha: str | None = None
    valor: float
    moneda: str
    cuenta: str
    clase_movimiento: str | None = None
    lugar_transaccion: str | None = None


def _parse_tx_datetime(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value)
    except ValueError:
        return None


@router.get("/messages")
def list_gmail_messages(
    since_date: str | None = Query(default=None, description="Fecha mínima YYYY-MM-DD"),
    max_emails: int = Query(default=50, ge=1, le=300),
    db: Session = Depends(get_db),
):
    parsed_since_date = None
    if since_date:
        try:
            parsed_since_date = datetime.strptime(since_date, "%Y-%m-%d")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="since_date debe estar en formato YYYY-MM-DD") from exc

    try:
        rows = web_scrapping_email.fetch_transactions(
            since_date=parsed_since_date,
            max_emails=max_emails,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error consultando Gmail: {exc}") from exc

    message_ids = [row.get("message_id") for row in rows if row.get("message_id")]
    imported_ids = set()
    if message_ids:
        imported_ids = {
            row[0] for row in db.query(Transaction.source_id)
            .filter(Transaction.source == EMAIL_SOURCE, Transaction.source_id.in_(message_ids))
            .all()
        }

    messages = []
    for row in rows:
        message_id = row.get("message_id")
        messages.append({
            **row,
            "already_imported": bool(message_id and message_id in imported_ids),
        })

    return {
        "total": len(messages),
        "messages": messages,
    }


@router.post("/manual-add")
def add_gmail_message_manually(payload: ManualGmailImportPayload, db: Session = Depends(get_db)):
    existing_tx = db.query(Transaction).filter_by(source=EMAIL_SOURCE, source_id=payload.message_id).first()
    if existing_tx:
        return {"success": True, "already_imported": True, "transaction_id": existing_tx.id}

    currency_code = (payload.moneda or "").upper()
    currency = db.query(Currency).filter_by(code=currency_code).first()
    if not currency:
        raise HTTPException(status_code=400, detail=f"Moneda '{currency_code}' no existe en la base")

    settings = get_settings()
    account = _resolve_account(db, payload.cuenta, currency.id, settings)
    if not account:
        raise HTTPException(status_code=400, detail=f"No se pudo resolver cuenta para '{payload.cuenta}'")

    tx_datetime = _parse_tx_datetime(payload.fecha)
    tx_date = tx_datetime.date() if tx_datetime else date.today()

    existing_email_row = db.query(EmailScrapeTransaction).filter_by(message_id=payload.message_id).first()
    if not existing_email_row:
        email_row = EmailScrapeTransaction(
            message_id=payload.message_id,
            transaction_date=tx_date,
            transaction_datetime=tx_datetime,
            amount=float(payload.valor or 0),
            currency=currency_code,
            account_label=payload.cuenta,
            movement_class=payload.clase_movimiento or None,
            location=payload.lugar_transaccion or None,
        )
        db.add(email_row)
        db.flush()

    memo = payload.clase_movimiento or None
    if payload.cuenta.upper() == "MASTERCARD_BLACK" and not memo:
        memo = "Mastercard Black"

    data = {
        "account_id": account.id,
        "date": tx_date,
        "payee_name": payload.lugar_transaccion or payload.cuenta,
        "memo": memo,
        "amount": -abs(float(payload.valor or 0)),
        "currency_id": currency.id,
        "cleared": False,
        "source": EMAIL_SOURCE,
        "source_id": payload.message_id,
    }

    try:
        tx = create_transaction(db, data)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"No se pudo crear la transacción: {exc}") from exc

    return {
        "success": True,
        "already_imported": False,
        "transaction_id": tx.id,
    }
