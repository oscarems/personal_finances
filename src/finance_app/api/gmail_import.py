from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models import Account, Category, Currency, Transaction
from finance_app.models.gmail_message import GmailProcessedMessage
from finance_app.models.merchant_rule import MerchantRule
from finance_app.services import gmail_ollama_service as ollama_svc
from finance_app.services.transaction_service import create_transaction

router = APIRouter()


class ConfirmPayload(BaseModel):
    message_id: str
    fecha: str
    monto: float
    moneda: str
    cuenta_id: int
    categoria_id: int | None = None
    comentario: str | None = None


class BulkConfirmItem(BaseModel):
    message_id: str
    fecha: str
    monto: float
    moneda: str
    cuenta_id: int
    categoria_id: int | None = None
    comentario: str | None = None


class BulkConfirmPayload(BaseModel):
    items: list[BulkConfirmItem]


@router.get("/models")
def list_models():
    try:
        return ollama_svc.list_ollama_models()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/emails")
def list_emails(
    since_date: str | None = None,
    max_emails: int = 50,
    db: Session = Depends(get_db),
):
    since = None
    if since_date:
        try:
            since = datetime.fromisoformat(since_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de fecha inválido. Use YYYY-MM-DD.")

    try:
        records = ollama_svc.fetch_and_store_emails(db, since_date=since, max_emails=max_emails)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return [r.to_dict() for r in records]


@router.post("/process/{message_id:path}")
def process_email(
    message_id: str,
    model: str | None = None,
    db: Session = Depends(get_db),
):
    record = db.query(GmailProcessedMessage).filter_by(message_id=message_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Correo no encontrado. Sincroniza primero.")

    accounts = [a.to_dict() for a in db.query(Account).filter_by(is_closed=False).all()]
    categories = [
        {"id": c.id, "name": c.name}
        for c in db.query(Category).filter_by(is_hidden=False).order_by(Category.name).all()
    ]
    merchant_rules = [r.to_dict() for r in db.query(MerchantRule).order_by(MerchantRule.merchant_name).all()]

    try:
        result = ollama_svc.call_ollama(record.body_text or "", accounts, categories, merchant_rules=merchant_rules, model=model)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Error llamando a Ollama: {exc}")

    return result


@router.post("/confirm")
def confirm_transaction(payload: ConfirmPayload, db: Session = Depends(get_db)):
    record = db.query(GmailProcessedMessage).filter_by(message_id=payload.message_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Correo no encontrado")
    if record.processed_at:
        raise HTTPException(status_code=409, detail="Este correo ya fue procesado")

    account = db.query(Account).get(payload.cuenta_id)
    if not account:
        raise HTTPException(status_code=400, detail="Cuenta no encontrada")

    currency = db.query(Currency).filter_by(code=payload.moneda).first()
    if not currency:
        raise HTTPException(status_code=400, detail=f"Moneda '{payload.moneda}' no encontrada")

    existing = db.query(Transaction).filter_by(
        source="gmail_ollama", source_id=payload.message_id
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Ya existe una transacción para este correo")

    try:
        tx = create_transaction(
            db,
            {
                "account_id": payload.cuenta_id,
                "date": datetime.fromisoformat(payload.fecha).date(),
                "payee_name": payload.comentario or "",
                "category_id": payload.categoria_id,
                "memo": payload.comentario,
                "amount": -abs(payload.monto),
                "currency_id": currency.id,
                "cleared": False,
                "source": "gmail_ollama",
                "source_id": payload.message_id,
            },
        )
        record.processed_at = datetime.utcnow()
        record.transaction_id = tx.id
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"No se pudo crear la transacción: {exc}")

    return {"message": "Transacción creada", "transaction": tx.to_dict()}


@router.get("/preview/{message_id:path}")
def preview_email(message_id: str, db: Session = Depends(get_db)):
    record = db.query(GmailProcessedMessage).filter_by(message_id=message_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Correo no encontrado")
    return {
        "message_id": record.message_id,
        "subject": record.subject,
        "sender": record.sender,
        "received_at": record.received_at.isoformat() if record.received_at else None,
        "body_text": record.body_text or "",
    }


@router.post("/bulk-confirm")
def bulk_confirm(payload: BulkConfirmPayload, db: Session = Depends(get_db)):
    results = []
    for item in payload.items:
        record = db.query(GmailProcessedMessage).filter_by(message_id=item.message_id).first()
        if not record:
            results.append({"message_id": item.message_id, "status": "error", "reason": "Correo no encontrado"})
            continue
        if record.processed_at:
            results.append({"message_id": item.message_id, "status": "skipped", "reason": "Ya procesado"})
            continue

        account = db.query(Account).get(item.cuenta_id)
        if not account:
            results.append({"message_id": item.message_id, "status": "error", "reason": "Cuenta no encontrada"})
            continue

        currency = db.query(Currency).filter_by(code=item.moneda).first()
        if not currency:
            results.append({"message_id": item.message_id, "status": "error", "reason": f"Moneda '{item.moneda}' no encontrada"})
            continue

        existing = db.query(Transaction).filter_by(source="gmail_ollama", source_id=item.message_id).first()
        if existing:
            results.append({"message_id": item.message_id, "status": "skipped", "reason": "Transacción duplicada"})
            continue

        try:
            tx = create_transaction(db, {
                "account_id": item.cuenta_id,
                "date": datetime.fromisoformat(item.fecha).date(),
                "payee_name": item.comentario or "",
                "category_id": item.categoria_id,
                "memo": item.comentario,
                "amount": -abs(item.monto),
                "currency_id": currency.id,
                "cleared": False,
                "source": "gmail_ollama",
                "source_id": item.message_id,
            })
            record.processed_at = datetime.utcnow()
            record.transaction_id = tx.id
            db.commit()
            results.append({"message_id": item.message_id, "status": "created", "transaction_id": tx.id})
        except Exception as exc:
            db.rollback()
            results.append({"message_id": item.message_id, "status": "error", "reason": str(exc)})

    return {"results": results}


def _delete_email_transactions(db: Session, message_id: str, linked_tx_id: int | None) -> list[int]:
    """Delete the linked transaction and any orphaned transactions with matching source_id."""
    deleted = []
    if linked_tx_id:
        tx = db.query(Transaction).get(linked_tx_id)
        if tx:
            deleted.append(tx.id)
            db.delete(tx)
    for tx in db.query(Transaction).filter_by(source="gmail_ollama", source_id=message_id).all():
        if tx.id not in deleted:
            deleted.append(tx.id)
            db.delete(tx)
    return deleted


@router.post("/reset/{message_id:path}")
def reset_email(message_id: str, db: Session = Depends(get_db)):
    record = db.query(GmailProcessedMessage).filter_by(message_id=message_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Correo no encontrado")

    deleted = _delete_email_transactions(db, message_id, record.transaction_id)
    record.processed_at = None
    record.skipped = False
    record.transaction_id = None
    db.commit()
    return {"message": "Correo restablecido", "deleted_transaction_ids": deleted}


@router.post("/bulk-reset")
def bulk_reset(payload: dict, db: Session = Depends(get_db)):
    message_ids: list[str] = payload.get("message_ids", [])
    results = []
    for mid in message_ids:
        record = db.query(GmailProcessedMessage).filter_by(message_id=mid).first()
        if not record:
            results.append({"message_id": mid, "status": "not_found"})
            continue

        deleted = _delete_email_transactions(db, mid, record.transaction_id)
        record.processed_at = None
        record.skipped = False
        record.transaction_id = None
        results.append({"message_id": mid, "status": "reset", "deleted_transaction_ids": deleted})

    db.commit()
    return {"results": results}


@router.post("/skip/{message_id:path}")
def skip_email(message_id: str, db: Session = Depends(get_db)):
    record = db.query(GmailProcessedMessage).filter_by(message_id=message_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Correo no encontrado")
    record.skipped = True
    db.commit()
    return {"message": "Correo omitido"}
