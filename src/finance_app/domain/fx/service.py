from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from finance_app.config import DEFAULT_EXCHANGE_RATES
from finance_app.database import SessionLocal
from finance_app.models import Currency, ExchangeRate

logger = logging.getLogger(__name__)

_QUANTIZE_COP = Decimal("0.01")


class FxRateUnavailableError(Exception):
    """No usable FX rate was found for the requested conversion."""


@dataclass(frozen=True)
class ConversionResult:
    """Result of a domain FX conversion with an explicit rate-source flag.

    ``rate_source`` values:
      - ``same_currency``: no conversion needed
      - ``service``: USD-pivot path via ``exchange_rate_service``
      - ``legacy``: direct CCY→COP / Currency / config default
      - ``fallback_identity``: no rate found; amount returned 1:1 (flagged)

    ``used_fallback`` is True only for ``fallback_identity``. Callers/UI should
    surface a warning when this is set — never treat it as a successful live rate.
    """

    amount: Decimal
    rate_source: str
    used_fallback: bool = False


def _decimalize(value: float | int | Decimal | None) -> Decimal:
    """Convert a numeric value to Decimal safely."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _quantize_cop(value: Decimal) -> Decimal:
    """Round a Decimal value to 2 decimal places."""
    return value.quantize(_QUANTIZE_COP, rounding=ROUND_HALF_UP)


def _legacy_rate_to_cop(db: Session, currency_code: str, as_of_date: date) -> Decimal | None:
    """Direct CCY→COP lookup used only if the USD-pivot converter is unavailable."""
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

    currency = db.query(Currency).filter_by(code=currency_code).first()
    if currency and currency.exchange_rate_to_base:
        return _decimalize(currency.exchange_rate_to_base)

    if currency_code in DEFAULT_EXCHANGE_RATES:
        return _decimalize(DEFAULT_EXCHANGE_RATES[currency_code])
    return None


def convert_to_cop_result(
    amount: float | int | Decimal,
    currency_code: str,
    as_of_date: date,
    db: Session | None = None,
    *,
    allow_identity_fallback: bool = True,
) -> ConversionResult:
    """Convert amount to COP and return amount + rate-source metadata."""
    amount_dec = _decimalize(amount)
    code = (currency_code or "COP").upper()
    if code == "COP":
        return ConversionResult(
            amount=_quantize_cop(amount_dec),
            rate_source="same_currency",
            used_fallback=False,
        )

    owns_session = db is None
    if db is None:
        db = SessionLocal()

    try:
        from finance_app.services.exchange_rate_service import (
            convert_currency_result,
        )

        try:
            converted, rate_meta = convert_currency_result(
                float(amount_dec),
                code,
                "COP",
                db,
                rate_date=as_of_date,
            )
            if rate_meta.used_fallback:
                logger.warning(
                    "FX convert_to_cop(%s→COP): exchange_rate_service used identity "
                    "fallback (source=%s)",
                    code,
                    rate_meta.source,
                )
                if not allow_identity_fallback:
                    raise FxRateUnavailableError(
                        f"No FX rate available for {code}→COP"
                    )
                return ConversionResult(
                    amount=_quantize_cop(_decimalize(converted)),
                    rate_source="fallback_identity",
                    used_fallback=True,
                )
            return ConversionResult(
                amount=_quantize_cop(_decimalize(converted)),
                rate_source="service",
                used_fallback=False,
            )
        except FxRateUnavailableError:
            raise
        except Exception as exc:
            legacy = _legacy_rate_to_cop(db, code, as_of_date)
            if legacy is None:
                logger.warning(
                    "FX convert_to_cop(%s→COP): no rate after service error (%s); "
                    "identity fallback",
                    code,
                    exc,
                )
                if not allow_identity_fallback:
                    raise FxRateUnavailableError(
                        f"No FX rate available for {code}→COP"
                    ) from exc
                return ConversionResult(
                    amount=_quantize_cop(amount_dec),
                    rate_source="fallback_identity",
                    used_fallback=True,
                )
            return ConversionResult(
                amount=_quantize_cop(amount_dec * legacy),
                rate_source="legacy",
                used_fallback=False,
            )
    finally:
        if owns_session:
            db.close()


def convert_to_cop(
    amount: float | int | Decimal,
    currency_code: str,
    as_of_date: date,
    db: Session | None = None,
) -> Decimal:
    """
    Convert amount to COP via the shared USD-pivot FX path.

    Uses ``exchange_rate_service.convert_currency`` (same rates as budgets/transfers).
    Falls back to a direct CCY→COP row / Currency.exchange_rate_to_base / config
    defaults only if that path raises.

    If no rate exists at all, returns the amount unchanged (identity) **and**
    logs a warning. Prefer ``convert_to_cop_result`` when the caller needs the
    ``used_fallback`` / ``rate_source`` flag.
    """
    return convert_to_cop_result(amount, currency_code, as_of_date, db=db).amount


def convert_from_cop_result(
    amount_cop: Decimal,
    currency_code: str,
    as_of_date: date,
    db: Session | None = None,
    *,
    allow_identity_fallback: bool = True,
) -> ConversionResult:
    """Convert COP amount into the target currency with rate-source metadata."""
    amount_dec = _decimalize(amount_cop)
    code = (currency_code or "COP").upper()
    if code == "COP":
        return ConversionResult(
            amount=amount_dec,
            rate_source="same_currency",
            used_fallback=False,
        )

    owns_session = db is None
    if db is None:
        db = SessionLocal()

    try:
        from finance_app.services.exchange_rate_service import (
            convert_currency_result,
        )

        try:
            converted, rate_meta = convert_currency_result(
                float(amount_dec),
                "COP",
                code,
                db,
                rate_date=as_of_date,
            )
            if rate_meta.used_fallback:
                logger.warning(
                    "FX convert_from_cop(COP→%s): exchange_rate_service used identity "
                    "fallback (source=%s)",
                    code,
                    rate_meta.source,
                )
                if not allow_identity_fallback:
                    raise FxRateUnavailableError(
                        f"No FX rate available for COP→{code}"
                    )
                return ConversionResult(
                    amount=_decimalize(converted),
                    rate_source="fallback_identity",
                    used_fallback=True,
                )
            return ConversionResult(
                amount=_decimalize(converted),
                rate_source="service",
                used_fallback=False,
            )
        except FxRateUnavailableError:
            raise
        except Exception as exc:
            legacy = _legacy_rate_to_cop(db, code, as_of_date)
            if legacy is None or legacy == 0:
                logger.warning(
                    "FX convert_from_cop(COP→%s): no rate after service error (%s); "
                    "identity fallback",
                    code,
                    exc,
                )
                if not allow_identity_fallback:
                    raise FxRateUnavailableError(
                        f"No FX rate available for COP→{code}"
                    ) from exc
                return ConversionResult(
                    amount=amount_dec,
                    rate_source="fallback_identity",
                    used_fallback=True,
                )
            return ConversionResult(
                amount=amount_dec / legacy,
                rate_source="legacy",
                used_fallback=False,
            )
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
    return convert_from_cop_result(amount_cop, currency_code, as_of_date, db=db).amount
