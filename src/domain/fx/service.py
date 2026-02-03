from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy.orm import Session

from config import DEFAULT_EXCHANGE_RATES
from finance_app.database import SessionLocal
from finance_app.models import Currency, ExchangeRate

_QUANTIZE_COP = Decimal("0.01")


def _decimalize(value: float | int | Decimal | None) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _quantize_cop(value: Decimal) -> Decimal:
    return value.quantize(_QUANTIZE_COP, rounding=ROUND_HALF_UP)


def _get_rate_from_exchange_table(
    db: Session,
    currency_code: str,
    as_of_date: date,
) -> Optional[Decimal]:
    if currency_code == "COP":
        return Decimal("1")

    rate_row = (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.from_currency == currency_code,
            ExchangeRate.to_currency == "COP",
            ExchangeRate.date <= as_of_date,
        )
        .order_by(ExchangeRate.date.desc())
        .first()
    )
    if rate_row:
        return _decimalize(rate_row.rate)
    return None


def _get_rate_from_currency_table(db: Session, currency_code: str) -> Optional[Decimal]:
    if currency_code == "COP":
        return Decimal("1")
    currency = db.query(Currency).filter_by(code=currency_code).first()
    if currency and currency.exchange_rate_to_base:
        return _decimalize(currency.exchange_rate_to_base)
    return None


def _get_rate_from_defaults(currency_code: str) -> Optional[Decimal]:
    if currency_code in DEFAULT_EXCHANGE_RATES:
        return _decimalize(DEFAULT_EXCHANGE_RATES[currency_code])
    return None


def _resolve_rate_to_cop(
    db: Session,
    currency_code: str,
    as_of_date: date,
) -> Decimal:
    return (
        _get_rate_from_exchange_table(db, currency_code, as_of_date)
        or _get_rate_from_currency_table(db, currency_code)
        or _get_rate_from_defaults(currency_code)
        or Decimal("1")
    )


def convert_to_cop(
    amount: float | int | Decimal,
    currency_code: str,
    as_of_date: date,
    db: Session | None = None,
) -> Decimal:
    """
    Convert amount to COP using available FX rules.

    Order of precedence:
    1) ExchangeRate table (latest on or before as_of_date)
    2) Currency.exchange_rate_to_base
    3) DEFAULT_EXCHANGE_RATES fallback
    """
    amount_dec = _decimalize(amount)
    if currency_code == "COP":
        return _quantize_cop(amount_dec)

    owns_session = db is None
    if db is None:
        db = SessionLocal()

    try:
        rate = _resolve_rate_to_cop(db, currency_code, as_of_date)
        return _quantize_cop(amount_dec * rate)
    finally:
        if owns_session:
            db.close()


def convert_from_cop(
    amount_cop: Decimal,
    currency_code: str,
    as_of_date: date,
    db: Session | None = None,
) -> Decimal:
    """Convert COP amount into the target currency using the same FX source."""
    amount_dec = _decimalize(amount_cop)
    if currency_code == "COP":
        return amount_dec

    owns_session = db is None
    if db is None:
        db = SessionLocal()

    try:
        rate = _resolve_rate_to_cop(db, currency_code, as_of_date)
        if rate == 0:
            return amount_dec
        return amount_dec / rate
    finally:
        if owns_session:
            db.close()
