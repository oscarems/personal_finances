from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from finance_app.models import Account, Category, Currency, TelegramSettings
from finance_app.services.transaction_service import create_transaction, create_transfer

KEY_ALIASES = {
    "cuenta": "account",
    "account": "account",
    "categoria": "category",
    "category": "category",
    "memo": "memo",
    "nota": "memo",
    "payee": "payee",
    "beneficiario": "payee",
    "fecha": "date",
    "desde": "from_account",
    "origen": "from_account",
    "hacia": "to_account",
    "destino": "to_account",
    "moneda": "currency",
}

MESSAGE_PATTERN = re.compile(r"(\w+)\s*:\s*([^:]+?)(?=\s+\w+\s*:|$)")
AMOUNT_PATTERN = re.compile(r"(?P<amount>-?\d+(?:[.,]\d+)?)\s*(?P<currency>[A-Za-z]{3})?")


def get_or_create_settings(db: Session) -> TelegramSettings:
    settings = db.query(TelegramSettings).first()
    if settings:
        return settings
    settings = TelegramSettings(is_active=False)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def update_settings(db: Session, payload: dict) -> TelegramSettings:
    settings = get_or_create_settings(db)
    for field in (
        "bot_token",
        "chat_id",
        "default_account_id",
        "default_category_id",
        "default_currency_id",
        "default_transfer_from_account_id",
        "default_transfer_to_account_id",
        "is_active",
    ):
        if field in payload:
            setattr(settings, field, payload[field])
    db.commit()
    db.refresh(settings)
    return settings


def parse_message(text: str) -> Tuple[str, dict]:
    if not text:
        raise ValueError("El mensaje está vacío.")
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("El mensaje está vacío.")

    command = cleaned.split()[0].lower().lstrip("/")
    if command in {"help", "ayuda"}:
        return "help", {}

    message_type = command
    data: dict = {}

    for raw_key, raw_value in MESSAGE_PATTERN.findall(cleaned):
        key = KEY_ALIASES.get(raw_key.lower())
        if not key:
            continue
        data[key] = raw_value.strip()

    cleaned_without_pairs = MESSAGE_PATTERN.sub("", cleaned)

    amount = None
    currency = None
    for match in AMOUNT_PATTERN.finditer(cleaned_without_pairs):
        amount_raw = match.group("amount")
        if amount_raw:
            amount = float(amount_raw.replace(",", "."))
            currency = match.group("currency")
            break

    if amount is not None:
        data["amount"] = amount
    if currency:
        data["currency"] = currency.upper()

    return message_type, data


def resolve_account_by_name(db: Session, name: str) -> Optional[Account]:
    if not name:
        return None
    return db.query(Account).filter(Account.name.ilike(name)).first()


def resolve_category_by_name(db: Session, name: str) -> Optional[Category]:
    if not name:
        return None
    return db.query(Category).filter(Category.name.ilike(name)).first()


def resolve_currency_by_code(db: Session, code: str) -> Optional[Currency]:
    if not code:
        return None
    return db.query(Currency).filter(Currency.code.ilike(code)).first()


def _parse_date(value: Optional[str]) -> date:
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("Formato de fecha inválido. Usa YYYY-MM-DD.") from exc


def build_transaction_from_message(db: Session, settings: TelegramSettings, message_type: str, data: dict):
    transaction_date = _parse_date(data.get("date"))
    currency = resolve_currency_by_code(db, data.get("currency")) if data.get("currency") else None

    if message_type in {"gasto", "egreso", "expense"}:
        account = resolve_account_by_name(db, data.get("account")) or (
            db.query(Account).get(settings.default_account_id)
        )
        if not account:
            raise ValueError("Define una cuenta por defecto o especifica cuenta:Nombre.")
        category = resolve_category_by_name(db, data.get("category")) or (
            db.query(Category).get(settings.default_category_id)
        )
        if not category:
            raise ValueError("Define una categoría por defecto o especifica categoria:Nombre.")
        amount = data.get("amount")
        if amount is None:
            raise ValueError("Incluye el monto. Ejemplo: gasto 12000 COP ...")
        if amount > 0:
            amount = -amount
        currency = currency or db.query(Currency).get(settings.default_currency_id)
        if not currency:
            currency = account.currency
        payload = {
            "account_id": account.id,
            "date": transaction_date,
            "payee_name": data.get("payee"),
            "category_id": category.id,
            "memo": data.get("memo"),
            "amount": amount,
            "currency_id": currency.id,
            "cleared": False,
        }
        return "transaction", create_transaction(db, payload)

    if message_type in {"ingreso", "income"}:
        account = resolve_account_by_name(db, data.get("account")) or (
            db.query(Account).get(settings.default_account_id)
        )
        if not account:
            raise ValueError("Define una cuenta por defecto o especifica cuenta:Nombre.")
        category = resolve_category_by_name(db, data.get("category")) or (
            db.query(Category).get(settings.default_category_id)
        )
        if not category:
            raise ValueError("Define una categoría por defecto o especifica categoria:Nombre.")
        amount = data.get("amount")
        if amount is None:
            raise ValueError("Incluye el monto. Ejemplo: ingreso 12000 COP ...")
        if amount < 0:
            amount = abs(amount)
        currency = currency or db.query(Currency).get(settings.default_currency_id)
        if not currency:
            currency = account.currency
        payload = {
            "account_id": account.id,
            "date": transaction_date,
            "payee_name": data.get("payee"),
            "category_id": category.id,
            "memo": data.get("memo"),
            "amount": amount,
            "currency_id": currency.id,
            "cleared": False,
        }
        return "transaction", create_transaction(db, payload)

    if message_type in {"transferencia", "transfer", "transferir"}:
        from_account = resolve_account_by_name(db, data.get("from_account")) or (
            db.query(Account).get(settings.default_transfer_from_account_id)
        )
        to_account = resolve_account_by_name(db, data.get("to_account")) or (
            db.query(Account).get(settings.default_transfer_to_account_id)
        )
        if not from_account or not to_account:
            raise ValueError("Define cuentas origen/destino o configura valores por defecto.")
        amount = data.get("amount")
        if amount is None:
            raise ValueError("Incluye el monto. Ejemplo: transferencia 50000 COP ...")
        if amount < 0:
            amount = abs(amount)
        from_currency = currency or from_account.currency
        to_currency = to_account.currency
        payload = {
            "from_account_id": from_account.id,
            "to_account_id": to_account.id,
            "date": transaction_date,
            "amount": amount,
            "from_currency_id": from_currency.id,
            "to_currency_id": to_currency.id,
            "memo": data.get("memo"),
            "cleared": False,
        }
        return "transfer", create_transfer(db, payload)

    raise ValueError("Tipo no reconocido. Usa gasto, ingreso o transferencia.")
