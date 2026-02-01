from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.telegram_service import (
    build_transaction_from_message,
    fetch_updates,
    get_or_create_settings,
    parse_message,
    update_settings,
)


router = APIRouter()


class TelegramSettingsPayload(BaseModel):
    bot_token: str | None = None
    chat_id: str | None = None
    default_account_id: int | None = None
    default_category_id: int | None = None
    default_currency_id: int | None = None
    default_transfer_from_account_id: int | None = None
    default_transfer_to_account_id: int | None = None
    is_active: bool | None = None
    llm_enabled: bool | None = None
    llm_model: str | None = None


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    settings = get_or_create_settings(db)
    return settings.to_dict()


@router.post("/settings")
def save_settings(payload: TelegramSettingsPayload, db: Session = Depends(get_db)):
    settings = update_settings(db, payload.dict(exclude_unset=True))
    return settings.to_dict()


@router.post("/webhook")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    settings = get_or_create_settings(db)
    if not settings.is_active:
        raise HTTPException(status_code=400, detail="Integración Telegram desactivada.")

    payload = await request.json()
    message = payload.get("message") or payload.get("edited_message")
    if not message or "text" not in message:
        return {"status": "ignored"}

    if settings.chat_id:
        incoming_chat_id = str(message.get("chat", {}).get("id", ""))
        if incoming_chat_id != str(settings.chat_id):
            raise HTTPException(status_code=403, detail="Chat no autorizado.")

    try:
        message_type, data = parse_message(message.get("text", ""))
        if message_type == "help":
            return {
                "status": "ok",
                "message": "Formato: gasto/ingreso/transferencia 12000 COP "
                "cuenta:Cuenta categoria:Categoria memo:Nota fecha:YYYY-MM-DD"
            }
        result_type, result = build_transaction_from_message(db, settings, message_type, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result_type == "transfer":
        return {
            "status": "ok",
            "transfer": [tx.to_dict() for tx in result],
        }

    return {"status": "ok", "transaction": result.to_dict()}


@router.post("/poll")
def poll_updates(db: Session = Depends(get_db), limit: int = 100):
    settings = get_or_create_settings(db)
    if not settings.is_active:
        raise HTTPException(status_code=400, detail="Integración Telegram desactivada.")

    try:
        result = fetch_updates(db, settings, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Error al consultar Telegram.") from exc

    return {"status": "ok", **result}
