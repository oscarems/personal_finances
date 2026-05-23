"""
Exchange Rate Service — multi-currency support.

Rates are stored as USD→X (1 USD = X foreign), with USD used as the universal
pivot for cross-currency conversion.

Backward-compatible API:
  get_current_exchange_rate(db)  → float (USD→base_currency rate, or USD→COP fallback)
  get_rate_for_date(db, date)    → float (same, for a historical date)
  convert_currency(amount, from_code, to_code, db, rate_date) → float
"""
from datetime import date, timedelta
from typing import Optional
import logging

import requests
from sqlalchemy.orm import Session
from sqlalchemy import desc

from finance_app.models import ExchangeRate, Currency
from finance_app.config import EXCHANGE_RATE_API

logger = logging.getLogger(__name__)

_PLAUSIBLE_MIN = 1e-6
_PLAUSIBLE_MAX = 1e9


# ---------------------------------------------------------------------------
# Low-level API fetch
# ---------------------------------------------------------------------------

def _fetch_usd_rates_from_api(api_url: str, timeout: int = 5) -> Optional[dict[str, float]]:
    """
    Fetch all rates relative to USD from a public API.
    Returns {currency_code: rate} where 1 USD = rate X, or None on failure.
    """
    try:
        response = requests.get(api_url, timeout=timeout)
        if response.status_code != 200:
            return None
        data = response.json()
        for key in ('rates', 'conversion_rates'):
            if key in data and isinstance(data[key], dict):
                return {k: float(v) for k, v in data[key].items() if isinstance(v, (int, float))}
    except Exception as e:
        logger.warning("Error fetching rates from %s: %s", api_url, e)
    return None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _active_currency_codes(db: Session) -> list[str]:
    """Return codes of all non-base currencies currently in the DB."""
    currencies = db.query(Currency).all()
    return [c.code for c in currencies if not c.is_base]


def _base_currency_code(db: Session) -> str:
    base = db.query(Currency).filter_by(is_base=True).first()
    return base.code if base else 'COP'


def _store_rate(db: Session, from_code: str, to_code: str, rate: float, today: date, source: str):
    """Upsert a rate record for today."""
    from sqlalchemy.exc import IntegrityError

    db.expire_all()
    existing = db.query(ExchangeRate).filter_by(
        from_currency=from_code, to_currency=to_code, date=today
    ).first()
    if existing:
        existing.rate = rate
        existing.source = source
        db.commit()
        return

    try:
        db.add(ExchangeRate(
            from_currency=from_code,
            to_currency=to_code,
            rate=rate,
            date=today,
            source=source,
        ))
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(ExchangeRate).filter_by(
            from_currency=from_code, to_currency=to_code, date=today
        ).first()
        if existing:
            existing.rate = rate
            existing.source = source
            db.commit()


def _get_stored_rate(db: Session, from_code: str, to_code: str, target_date: date) -> Optional[float]:
    """Look up an exact stored rate for a date."""
    r = db.query(ExchangeRate).filter_by(
        from_currency=from_code, to_currency=to_code, date=target_date
    ).first()
    return r.rate if r and _PLAUSIBLE_MIN <= r.rate <= _PLAUSIBLE_MAX else None


def _get_nearest_stored_rate(db: Session, from_code: str, to_code: str, before: date) -> Optional[float]:
    """Find the most recent stored rate on or before `before`."""
    r = (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.from_currency == from_code,
            ExchangeRate.to_currency == to_code,
            ExchangeRate.date <= before,
        )
        .order_by(desc(ExchangeRate.date))
        .first()
    )
    return r.rate if r and _PLAUSIBLE_MIN <= r.rate <= _PLAUSIBLE_MAX else None


def _average_recent_rate(db: Session, from_code: str, to_code: str, days: int = 5) -> Optional[float]:
    recent = (
        db.query(ExchangeRate)
        .filter_by(from_currency=from_code, to_currency=to_code)
        .order_by(desc(ExchangeRate.date))
        .limit(days)
        .all()
    )
    vals = [r.rate for r in recent if _PLAUSIBLE_MIN <= r.rate <= _PLAUSIBLE_MAX]
    return sum(vals) / len(vals) if vals else None


# ---------------------------------------------------------------------------
# Sync all rates on startup
# ---------------------------------------------------------------------------

def sync_all_currency_rates(db: Session, force: bool = False) -> None:
    """
    Fetch today's rates for all non-base currencies in the DB.
    Uses a single API call (USD base) and stores each pair.
    Called on app startup.
    """
    today = date.today()
    non_base_codes = _active_currency_codes(db)
    if not non_base_codes:
        return

    # Check if we already have today's rates for all currencies
    if not force:
        missing = [
            code for code in non_base_codes
            if _get_stored_rate(db, 'USD', code, today) is None
        ]
        if not missing:
            logger.info("Exchange rates already up to date for today.")
            return
    else:
        missing = non_base_codes

    config = EXCHANGE_RATE_API
    all_rates: Optional[dict[str, float]] = None

    # Try primary API
    for attempt in range(config['retries']):
        all_rates = _fetch_usd_rates_from_api(config['primary'], config['timeout'])
        if all_rates:
            break
        logger.warning("Primary exchange rate API attempt %d failed", attempt + 1)

    # Try fallback API
    if not all_rates:
        for attempt in range(config['retries']):
            all_rates = _fetch_usd_rates_from_api(config['fallback'], config['timeout'])
            if all_rates:
                break
            logger.warning("Fallback exchange rate API attempt %d failed", attempt + 1)

    source = 'api_primary' if all_rates else 'average'

    for code in missing:
        if all_rates and code in all_rates:
            rate = all_rates[code]
            if _PLAUSIBLE_MIN <= rate <= _PLAUSIBLE_MAX:
                _store_rate(db, 'USD', code, rate, today, source)
                logger.info("Stored rate USD→%s = %.4f", code, rate)
                continue

        # Fallback: use historical average or default
        avg = _average_recent_rate(db, 'USD', code)
        if avg:
            _store_rate(db, 'USD', code, avg, today, 'average')
            logger.info("Stored average rate USD→%s = %.4f", code, avg)
        else:
            from finance_app.config import DEFAULT_EXCHANGE_RATES_TO_USD
            default = DEFAULT_EXCHANGE_RATES_TO_USD.get(code, 1.0)
            _store_rate(db, 'USD', code, default, today, 'default')
            logger.info("Stored default rate USD→%s = %.4f", code, default)


# ---------------------------------------------------------------------------
# Generic rate lookup (USD pivot)
# ---------------------------------------------------------------------------

def get_rate(
    db: Session,
    from_code: str,
    to_code: str,
    target_date: Optional[date] = None,
) -> float:
    """
    Get the exchange rate to convert 1 unit of from_code into to_code.
    Uses USD as a universal pivot:
        rate(A→B) = rate(USD→B) / rate(USD→A)

    Falls back through: DB cache → API → historical average → config default.
    """
    if from_code == to_code:
        return 1.0

    lookup_date = target_date or date.today()

    def _usd_to(code: str) -> float:
        if code == 'USD':
            return 1.0
        # Exact date
        r = _get_stored_rate(db, 'USD', code, lookup_date)
        if r:
            return r
        # Nearest historical
        r = _get_nearest_stored_rate(db, 'USD', code, lookup_date)
        if r:
            return r
        # Live fetch (only for today)
        if not target_date or target_date == date.today():
            config = EXCHANGE_RATE_API
            for url in (config['primary'], config['fallback']):
                all_rates = _fetch_usd_rates_from_api(url, config['timeout'])
                if all_rates and code in all_rates:
                    rate = all_rates[code]
                    if _PLAUSIBLE_MIN <= rate <= _PLAUSIBLE_MAX:
                        _store_rate(db, 'USD', code, rate, date.today(), 'api_primary')
                        return rate
        # Average
        avg = _average_recent_rate(db, 'USD', code)
        if avg:
            return avg
        # Hard default
        from finance_app.config import DEFAULT_EXCHANGE_RATES_TO_USD
        return DEFAULT_EXCHANGE_RATES_TO_USD.get(code, 1.0)

    usd_to_from = _usd_to(from_code)
    usd_to_to   = _usd_to(to_code)

    if usd_to_from <= 0:
        return 1.0

    return usd_to_to / usd_to_from


# ---------------------------------------------------------------------------
# Backward-compatible public API
# ---------------------------------------------------------------------------

def _usd_cop_target(db: Session) -> str:
    """Return the non-USD currency code to use as the COP-equivalent target.

    When COP is the base currency (is_base=True) it won't appear in the non-base
    list, so we fall back to _base_currency_code() before scanning non-base currencies.
    """
    base = _base_currency_code(db)
    if base != 'USD':
        return base  # e.g. 'COP'
    non_base = _active_currency_codes(db)
    return 'COP' if 'COP' in non_base else (non_base[0] if non_base else 'COP')


def get_current_exchange_rate(db: Session, force_fetch: bool = False) -> float:
    """
    Returns the USD→COP rate (or USD→base_currency if COP is not present).
    Backward-compatible shim used throughout budget_service, etc.
    """
    if force_fetch:
        sync_all_currency_rates(db, force=True)
    return get_rate(db, 'USD', _usd_cop_target(db))


def get_rate_for_date(db: Session, target_date: date) -> float:
    """USD→COP (or USD→base_currency) rate for a historical date. Backward-compatible."""
    return get_rate(db, 'USD', _usd_cop_target(db), target_date)


def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
    db: Session,
    rate_date: Optional[date] = None,
) -> float:
    """Convert amount from from_currency to to_currency. Supports any pair."""
    if from_currency == to_currency:
        return amount
    rate = get_rate(db, from_currency, to_currency, rate_date)
    return amount * rate


# ---------------------------------------------------------------------------
# Legacy single-pair helpers (kept for any direct callers)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Historical rate import
# ---------------------------------------------------------------------------

_HISTORICAL_API_PRIMARY = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@{date}/v1/currencies/usd.json"
_HISTORICAL_API_FALLBACK = "https://{date}.currency-api.pages.dev/v1/currencies/usd.json"


def _fetch_historical_rates_for_date(target_date: date, timeout: int = 8) -> Optional[dict[str, float]]:
    """Fetch USD→all rates for a specific historical date from fawazahmed0 CDN API.

    Returns a dict of lowercase currency codes → rates, or None on failure.
    API is free, no key required, data available from 2023-01-01 onward.
    """
    date_str = target_date.isoformat()
    for url_template in (_HISTORICAL_API_PRIMARY, _HISTORICAL_API_FALLBACK):
        url = url_template.format(date=date_str)
        try:
            resp = requests.get(url, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                rates = data.get("usd", {})
                if rates:
                    return {k.upper(): float(v) for k, v in rates.items() if isinstance(v, (int, float))}
        except Exception as e:
            logger.warning("Historical rate fetch failed for %s from %s: %s", date_str, url, e)
    return None


def import_historical_rates(
    db: Session,
    from_date: date,
    to_date: date,
    currencies: Optional[list[str]] = None,
    only_missing: bool = True,
) -> dict:
    """Import historical USD→X rates for every date in [from_date, to_date].

    Args:
        db: Database session.
        from_date: Start of range (inclusive).
        to_date: End of range (inclusive).
        currencies: List of currency codes to import (e.g. ['COP', 'EUR']).
                    Defaults to all non-base currencies in the DB.
        only_missing: If True, skip dates that already have a stored rate.

    Returns:
        dict with 'imported', 'skipped', 'failed' counts and 'errors' list.
    """
    if currencies is None:
        all_codes = _active_currency_codes(db)
        base = _base_currency_code(db)
        currencies = [c for c in all_codes if c != 'USD'] or [base]

    results = {"imported": 0, "skipped": 0, "failed": 0, "errors": []}

    current = from_date
    while current <= to_date:
        # Skip weekends — markets closed, API uses Friday's rate anyway
        if current.weekday() < 5:  # Monday=0 ... Friday=4
            missing = []
            if only_missing:
                for code in currencies:
                    if _get_stored_rate(db, 'USD', code, current) is None:
                        missing.append(code)
            else:
                missing = list(currencies)

            if missing:
                rates = _fetch_historical_rates_for_date(current)
                if rates:
                    for code in missing:
                        rate = rates.get(code)
                        if rate and _PLAUSIBLE_MIN <= rate <= _PLAUSIBLE_MAX:
                            _store_rate(db, 'USD', code, rate, current, 'historical_api')
                            results["imported"] += 1
                        else:
                            results["failed"] += 1
                            results["errors"].append(f"{current}: no rate for {code}")
                else:
                    results["failed"] += len(missing)
                    results["errors"].append(f"{current}: API returned no data")
            else:
                results["skipped"] += len(currencies)
        else:
            results["skipped"] += len(currencies)

        current += timedelta(days=1)

    return results


def import_historical_rates_for_transactions(db: Session) -> dict:
    """Import historical rates only for dates that have transactions but no stored rate.

    More efficient than a full date-range import — only fetches what's needed.
    """
    from finance_app.models import Transaction
    from sqlalchemy import distinct

    all_codes = _active_currency_codes(db)
    base = _base_currency_code(db)
    currencies = [c for c in all_codes if c != 'USD'] or [base]

    tx_dates = [
        d for (d,) in db.query(distinct(Transaction.date)).order_by(Transaction.date).all()
    ]

    results = {"imported": 0, "skipped": 0, "failed": 0, "errors": [], "dates_checked": len(tx_dates)}

    for tx_date in tx_dates:
        missing = [c for c in currencies if _get_stored_rate(db, 'USD', c, tx_date) is None]
        if not missing:
            results["skipped"] += len(currencies)
            continue

        rates = _fetch_historical_rates_for_date(tx_date)
        if rates:
            for code in missing:
                rate = rates.get(code)
                if rate and _PLAUSIBLE_MIN <= rate <= _PLAUSIBLE_MAX:
                    _store_rate(db, 'USD', code, rate, tx_date, 'historical_api')
                    results["imported"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append(f"{tx_date}: no rate for {code}")
        else:
            results["failed"] += len(missing)
            results["errors"].append(f"{tx_date}: API returned no data")

    return results


def fetch_rate_from_api(api_url: str, timeout: int = 5) -> Optional[float]:
    """Legacy: fetch USD→COP rate from a specific URL."""
    rates = _fetch_usd_rates_from_api(api_url, timeout)
    if rates and 'COP' in rates:
        return rates['COP']
    return None


def get_average_recent_rates(db: Session, days: int = 5) -> Optional[float]:
    """Legacy: average of recent USD→COP rates."""
    return _average_recent_rate(db, 'USD', 'COP', days)


def is_rate_plausible(rate: Optional[float]) -> bool:
    if rate is None:
        return False
    return _PLAUSIBLE_MIN <= rate <= _PLAUSIBLE_MAX
