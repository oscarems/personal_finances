from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from finance_app.config import get_telegram_config, get_telegram_status
from finance_app.database import get_db
from finance_app.services.telegram_service import (
    build_transaction_from_message,
    get_or_create_settings,
    parse_message,
    update_settings,
)


router = APIRouter()


class TelegramSettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bot_token: str | None = None
    chat_id: str | None = None
    default_account_id: int | None = None
    default_category_id: int | None = None
    default_currency_id: int | None = None
    default_transfer_from_account_id: int | None = None
    default_transfer_to_account_id: int | None = None
    is_active: bool | None = None


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    settings = get_or_create_settings(db)
    return settings.to_dict()


@router.post("/settings")
def save_settings(payload: TelegramSettingsPayload, db: Session = Depends(get_db)):
    raw_payload = payload.model_dump(exclude_unset=True)
    if "bot_token" in raw_payload or "chat_id" in raw_payload:
        raise HTTPException(status_code=400, detail="No se permiten secretos en la configuración.")
    settings = update_settings(db, raw_payload)
    return settings.to_dict()


@router.get("/status")
def telegram_status(db: Session = Depends(get_db)):
    status = get_telegram_status()
    settings = get_or_create_settings(db)
    return {
        "configured": status["configured"],
        "active": settings.is_active if settings else False,
        "message": status["message"],
        "masked_token": status["masked_token"],
        "chat_id": status["masked_chat_id"],
    }


@router.post("/webhook")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    settings = get_or_create_settings(db)
    env_config = get_telegram_config()
    if not env_config:
        raise HTTPException(status_code=400, detail="Integración Telegram no configurada.")
    if not settings.is_active:
        raise HTTPException(status_code=400, detail="Integración Telegram desactivada.")

    payload = await request.json()
    message = payload.get("message") or payload.get("edited_message")
    if not message or "text" not in message:
        return {"status": "ignored"}

    if env_config.chat_id:
        incoming_chat_id = str(message.get("chat", {}).get("id", ""))
        if incoming_chat_id != str(env_config.chat_id):
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
