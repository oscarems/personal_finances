import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from finance_app.database import default_database_name, ensure_database_initialized, get_session_factory
from finance_app.models import Account, Category, Currency, TelegramSettings, Transaction
from finance_app.services.transaction_service import create_transaction


LOGGER = logging.getLogger("finance_app.sync.telegram")

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
AMOUNT_PATTERN = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")
TELEGRAM_SOURCE = "telegram"


@dataclass
class ParsedMessage:
    account_id: int
    amount: float
    currency_id: int
    payee_name: str
    category_id: Optional[int]
    memo: Optional[str]
    transaction_date: date


def _normalize_name(value: str) -> str:
    return value.strip().lower()


def _get_default_account(db: Session, default_account_name: str) -> Optional[Account]:
    if not default_account_name:
        return None
    normalized = _normalize_name(default_account_name)
    return db.query(Account).filter(text("lower(name) = :name")).params(name=normalized).first()


def _get_currency_map(db: Session) -> dict[str, Currency]:
    return {currency.code.upper(): currency for currency in db.query(Currency).all()}


def _get_category_map(db: Session) -> dict[str, Category]:
    return {category.name.lower(): category for category in db.query(Category).all()}


def _parse_amount(token: str) -> Optional[float]:
    if not AMOUNT_PATTERN.match(token):
        return None
    normalized = token.replace(",", ".")
    try:
        amount = float(normalized)
    except ValueError:
        return None
    if token.startswith(("+", "-")):
        return amount
    return -abs(amount)


def _parse_message(
    db: Session,
    text_message: str,
    default_currency: Currency,
    default_account: Account,
    currency_map: dict[str, Currency],
    category_map: dict[str, Category]
) -> Optional[ParsedMessage]:
    tokens = text_message.strip().split()
    if not tokens:
        return None

    token_index = 0
    transaction_date = date.today()
    if DATE_PATTERN.match(tokens[token_index]):
        try:
            transaction_date = date.fromisoformat(tokens[token_index])
        except ValueError:
            return None
        token_index += 1

    if token_index >= len(tokens):
        return None

    amount = _parse_amount(tokens[token_index])
    if amount is None:
        return None
    token_index += 1

    currency = default_currency
    if token_index < len(tokens):
        currency_candidate = tokens[token_index]
        if currency_candidate.isalpha() and not currency_candidate.startswith("@"):
            candidate_key = currency_candidate.upper()
            if candidate_key in currency_map:
                currency = currency_map[candidate_key]
                token_index += 1

    account = default_account
    if token_index < len(tokens) and tokens[token_index].startswith("@"):
        account_candidate = _normalize_name(tokens[token_index][1:])
        account_match = db.query(Account).filter(text("lower(name) = :name")).params(name=account_candidate).first()
        if account_match:
            account = account_match
        else:
            LOGGER.warning("Cuenta '%s' no encontrada. Usando cuenta por defecto '%s'.", account_candidate, account.name)
        token_index += 1

    if token_index >= len(tokens):
        return None

    remaining = tokens[token_index:]
    payee_name = remaining[0]
    category_id = None
    memo_tokens = remaining[1:]

    if remaining:
        category_candidate = remaining[-1].lower()
        category_match = category_map.get(category_candidate)
        if category_match:
            category_id = category_match.id
            memo_tokens = remaining[1:-1]

    memo = " ".join(memo_tokens).strip() or None

    return ParsedMessage(
        account_id=account.id,
        amount=amount,
        currency_id=currency.id,
        payee_name=payee_name,
        category_id=category_id,
        memo=memo,
        transaction_date=transaction_date
    )


def _ensure_transaction_source_columns(db: Session) -> bool:
    engine = db.get_bind()
    if engine.url.drivername != "sqlite":
        return True
    with engine.begin() as connection:
        columns = connection.execute(text("PRAGMA table_info(transactions)")).fetchall()
    column_names = {row[1] for row in columns}
    return {"source", "source_id"}.issubset(column_names)


def _load_settings(db: Session) -> TelegramSettings:
    settings = db.query(TelegramSettings).order_by(TelegramSettings.id.asc()).first()
    if settings:
        return settings
    settings = TelegramSettings(is_active=True)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def _get_updates(token: str, offset: Optional[int]) -> list[dict]:
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"timeout": 0}
    if offset is not None:
        params["offset"] = offset
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise ValueError(f"Telegram API error: {payload}")
    return payload.get("result", [])


def _get_default_currency(db: Session, default_currency_code: str) -> Optional[Currency]:
    if default_currency_code:
        return db.query(Currency).filter(text("upper(code) = :code")).params(code=default_currency_code.upper()).first()
    return db.query(Currency).filter_by(is_base=True).first()


def sync_telegram_messages() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    allowed_chat_id = os.getenv("TELEGRAM_ALLOWED_CHAT_ID")
    default_currency_code = os.getenv("TELEGRAM_DEFAULT_CURRENCY")
    default_account_name = os.getenv("TELEGRAM_DEFAULT_ACCOUNT")

    if not token or not allowed_chat_id:
        LOGGER.error("Faltan TELEGRAM_BOT_TOKEN o TELEGRAM_ALLOWED_CHAT_ID.")
        return 1

    try:
        allowed_chat_id_int = int(allowed_chat_id)
    except ValueError:
        LOGGER.error("TELEGRAM_ALLOWED_CHAT_ID debe ser numérico.")
        return 1

    db_name = default_database_name()
    ensure_database_initialized(db_name)
    session_factory = get_session_factory(db_name)
    db = session_factory()

    try:
        if not _ensure_transaction_source_columns(db):
            LOGGER.error(
                "La base de datos no tiene columnas source/source_id. "
                "Ejecuta la migración opcional antes de sincronizar."
            )
            return 1

        default_currency = _get_default_currency(db, default_currency_code)
        if not default_currency:
            LOGGER.error("No se pudo determinar la moneda por defecto.")
            return 1

        default_account = _get_default_account(db, default_account_name or "")
        if not default_account:
            LOGGER.error("No se encontró la cuenta por defecto '%s'.", default_account_name)
            return 1

        currency_map = _get_currency_map(db)
        category_map = _get_category_map(db)
        settings = _load_settings(db)
        offset = settings.last_update_id + 1 if settings.last_update_id is not None else None

        updates = _get_updates(token, offset)
        total_updates = len(updates)
        inserted = 0
        ignored = 0
        max_update_id = settings.last_update_id or 0

        for update in updates:
            update_id = update.get("update_id")
            if update_id is None:
                ignored += 1
                continue
            max_update_id = max(max_update_id, update_id)

            message = update.get("message") or update.get("edited_message")
            if not message:
                ignored += 1
                continue
            chat = message.get("chat", {})
            if chat.get("id") != allowed_chat_id_int:
                ignored += 1
                continue
            text_message = message.get("text")
            if not text_message:
                ignored += 1
                continue

            parsed = _parse_message(
                db=db,
                text_message=text_message,
                default_currency=default_currency,
                default_account=default_account,
                currency_map=currency_map,
                category_map=category_map
            )
            if not parsed:
                LOGGER.warning("Mensaje inválido ignorado: %s", text_message)
                ignored += 1
                continue

            existing = db.query(Transaction).filter_by(
                source=TELEGRAM_SOURCE,
                source_id=str(update_id)
            ).first()
            if existing:
                ignored += 1
                continue

            data = {
                "account_id": parsed.account_id,
                "date": parsed.transaction_date,
                "payee_name": parsed.payee_name,
                "category_id": parsed.category_id,
                "memo": parsed.memo,
                "amount": parsed.amount,
                "currency_id": parsed.currency_id,
                "cleared": False,
                "source": TELEGRAM_SOURCE,
                "source_id": str(update_id)
            }
            try:
                create_transaction(db, data)
                db.commit()
                inserted += 1
            except Exception as exc:
                db.rollback()
                LOGGER.warning("Error insertando transacción para update %s: %s", update_id, exc)
                ignored += 1

        if updates:
            settings.last_update_id = max_update_id
            db.add(settings)
            db.commit()

        LOGGER.info(
            "Telegram sync completado. Updates=%s Insertados=%s Ignorados=%s",
            total_updates,
            inserted,
            ignored
        )
        return 0
    finally:
        db.close()


def main() -> None:
    raise SystemExit(sync_telegram_messages())


if __name__ == "__main__":
    main()
