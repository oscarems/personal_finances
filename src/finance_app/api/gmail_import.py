from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

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
def list_gmail_messages():
    raise HTTPException(
        status_code=501,
        detail="Módulo de email scraping no disponible. Funcionalidad pendiente de reimplementación.",
    )


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
