"""
Exchange Rate Service — multi-currency support.

Rates are stored as USD→X (1 USD = X foreign), with USD used as the universal
pivot for cross-currency conversion.

Backward-compatible API:
  get_current_exchange_rate(db)  → float (USD→base_currency rate, or USD→COP fallback)
  get_rate_for_date(db, date)    → float (same, for a historical date)
  convert_currency(amount, from_code, to_code, db, rate_date) → float
  convert_currency_result(...) → (amount, RateResult) with fallback flag
"""
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
import logging
import os
import ssl

import requests
from requests.adapters import HTTPAdapter
from sqlalchemy.orm import Session
from sqlalchemy import desc

from finance_app.models import ExchangeRate, Currency
from finance_app.config import EXCHANGE_RATE_API

logger = logging.getLogger(__name__)

_PLAUSIBLE_MIN = 1e-6
_PLAUSIBLE_MAX = 1e9
_STALE_RATE_DAYS = 1  # a cached rate older than this triggers a live re-fetch


@dataclass(frozen=True)
class RateResult:
    """Exchange-rate lookup with an explicit source flag.

    ``source`` values: ``identity`` (same currency), ``cache``, ``api``,
    ``stale_cache``, ``average``, ``default``, ``fallback_identity``.
    ``used_fallback`` is True only when the rate is the silent 1.0 identity used
    because no rate could be resolved — callers should warn the user.
    """

    rate: float
    source: str
    used_fallback: bool = False


# Extra CA certs some local security software injects for TLS inspection
# (e.g. Norton sets NODE_EXTRA_CA_CERTS for Node; Python has no equivalent
# built in, so `requests` fails TLS verification against those proxies).
# We merge them with certifi's bundle rather than disabling verification.
_EXTRA_CA_CANDIDATES = [
    os.environ.get('NODE_EXTRA_CA_CERTS'),
    os.environ.get('REQUESTS_CA_BUNDLE'),
    r'C:\ProgramData\Norton\Antivirus\wscert.pem',
]
_CA_BUNDLE_CACHE_PATH = Path(__file__).resolve().parent.parent / '.cache' / 'ca_bundle.pem'
_session: Optional[requests.Session] = None


class _TlsInspectionAdapter(HTTPAdapter):
    """HTTPAdapter using an SSLContext that trusts a local TLS-inspection CA.

    Some antivirus/corporate proxies (Norton included) issue CA certs whose
    Basic Constraints extension isn't marked critical — technically
    non-conformant to RFC 5280, but common in older MITM tooling. OpenSSL 3.x
    rejects those under VERIFY_X509_STRICT even once trusted, so we clear
    that single flag while still requiring full chain + hostname validation.
    """

    def __init__(self, ssl_context: ssl.SSLContext, *args, **kwargs):
        self._ssl_context = ssl_context
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs['ssl_context'] = self._ssl_context
        return super().init_poolmanager(*args, **kwargs)


def _get_requests_session() -> requests.Session:
    """Return a shared requests.Session, configured to trust a locally
    installed TLS-inspection CA (if any) in addition to the public CA bundle.
    Falls back to a plain Session (standard verification) when no such
    local CA is present.
    """
    global _session
    if _session is not None:
        return _session

    extra_ca = next((p for p in _EXTRA_CA_CANDIDATES if p and os.path.exists(p)), None)
    session = requests.Session()

    if extra_ca:
        try:
            import certifi
            certifi_bundle = Path(certifi.where()).read_text(encoding='utf-8')
            extra_pem = Path(extra_ca).read_text(encoding='utf-8')
            _CA_BUNDLE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _CA_BUNDLE_CACHE_PATH.write_text(certifi_bundle + '\n' + extra_pem, encoding='utf-8')

            ctx = ssl.create_default_context(cafile=str(_CA_BUNDLE_CACHE_PATH))
            ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
            session.mount('https://', _TlsInspectionAdapter(ctx))
            logger.info("Using combined CA bundle (certifi + %s) for exchange rate API calls", extra_ca)
        except Exception:
            logger.exception("Failed to build combined CA bundle from %s", extra_ca)

    _session = session
    return _session


# ---------------------------------------------------------------------------
# Low-level API fetch
# ---------------------------------------------------------------------------

def _fetch_usd_rates_from_api(api_url: str, timeout: int = 5) -> Optional[dict[str, float]]:
    """
    Fetch all rates relative to USD from a public API.
    Returns {currency_code: rate} where 1 USD = rate X, or None on failure.
    """
    try:
        response = _get_requests_session().get(api_url, timeout=timeout)
        if response.status_code != 200:
            logger.warning(
                "Exchange rate API %s returned status %d: %s",
                api_url, response.status_code, response.text[:200],
            )
            return None
        data = response.json()
        for key in ('rates', 'conversion_rates'):
            if key in data and isinstance(data[key], dict):
                return {k: float(v) for k, v in data[key].items() if isinstance(v, (int, float))}
        logger.warning("Exchange rate API %s response missing rates keys: %s", api_url, list(data.keys()))
    except Exception:
        logger.exception("Error fetching rates from %s", api_url)
    return None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _active_currency_codes(db: Session) -> list[str]:
    """Return codes of all non-USD currencies currently in the DB that need a USD pivot rate.

    Includes the base currency (e.g. COP) even though it's not "non-base" —
    the sync loop stores USD→code rates, and the base currency is exactly what
    convert_currency/get_current_exchange_rate need kept fresh.
    """
    currencies = db.query(Currency).all()
    return [c.code for c in currencies if c.code != 'USD']


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

def get_rate_result(
    db: Session,
    from_code: str,
    to_code: str,
    target_date: Optional[date] = None,
) -> RateResult:
    """
    Get the exchange rate to convert 1 unit of from_code into to_code,
    plus a source flag.

    Uses USD as a universal pivot:
        rate(A→B) = rate(USD→B) / rate(USD→A)

    Falls back through: DB cache → API → historical average → config default.
    Unknown currencies yield ``fallback_identity`` (rate=1.0) with a warning —
    never treat that as a successful live quote.
    """
    from_code = (from_code or "").upper()
    to_code = (to_code or "").upper()
    if from_code == to_code:
        return RateResult(rate=1.0, source="identity", used_fallback=False)

    lookup_date = target_date or date.today()
    is_live_lookup = not target_date or target_date == date.today()

    def _usd_to(code: str) -> RateResult:
        if code == "USD":
            return RateResult(rate=1.0, source="identity", used_fallback=False)
        # Exact date
        r = _get_stored_rate(db, "USD", code, lookup_date)
        if r:
            return RateResult(rate=r, source="cache", used_fallback=False)
        # Nearest historical — only good enough if it's recent (or we're
        # asking about a past date, where "nearest on/before" is correct by
        # definition). For today's lookups, a stale rate must not preempt a
        # live fetch.
        nearest_row = (
            db.query(ExchangeRate)
            .filter(
                ExchangeRate.from_currency == "USD",
                ExchangeRate.to_currency == code,
                ExchangeRate.date <= lookup_date,
            )
            .order_by(desc(ExchangeRate.date))
            .first()
        )
        nearest = (
            nearest_row.rate
            if nearest_row and _PLAUSIBLE_MIN <= nearest_row.rate <= _PLAUSIBLE_MAX
            else None
        )
        stale = (
            nearest_row is not None
            and (lookup_date - nearest_row.date).days > _STALE_RATE_DAYS
        )
        if nearest is not None and not (is_live_lookup and stale):
            return RateResult(rate=nearest, source="cache", used_fallback=False)
        # Live fetch (only for today, or when the cached rate is too stale)
        if is_live_lookup:
            config = EXCHANGE_RATE_API
            for url in (config["primary"], config["fallback"]):
                all_rates = _fetch_usd_rates_from_api(url, config["timeout"])
                if all_rates and code in all_rates:
                    rate = all_rates[code]
                    if _PLAUSIBLE_MIN <= rate <= _PLAUSIBLE_MAX:
                        _store_rate(db, "USD", code, rate, date.today(), "api_primary")
                        return RateResult(rate=rate, source="api", used_fallback=False)
        # Fall back to the stale cached rate rather than nothing
        if nearest is not None:
            return RateResult(rate=nearest, source="stale_cache", used_fallback=False)
        # Average
        avg = _average_recent_rate(db, "USD", code)
        if avg:
            return RateResult(rate=avg, source="average", used_fallback=False)
        # Hard default from config (known currencies)
        from finance_app.config import DEFAULT_EXCHANGE_RATES_TO_USD

        if code in DEFAULT_EXCHANGE_RATES_TO_USD:
            return RateResult(
                rate=DEFAULT_EXCHANGE_RATES_TO_USD[code],
                source="default",
                used_fallback=False,
            )
        logger.warning(
            "No FX rate for USD→%s; using identity 1.0 (fallback_identity)",
            code,
        )
        return RateResult(rate=1.0, source="fallback_identity", used_fallback=True)

    usd_to_from = _usd_to(from_code)
    usd_to_to = _usd_to(to_code)

    if usd_to_from.used_fallback or usd_to_to.used_fallback:
        logger.warning(
            "FX rate %s→%s unresolved (from_source=%s, to_source=%s); "
            "identity 1.0 fallback",
            from_code,
            to_code,
            usd_to_from.source,
            usd_to_to.source,
        )
        return RateResult(rate=1.0, source="fallback_identity", used_fallback=True)

    if usd_to_from.rate <= 0:
        logger.warning(
            "FX rate USD→%s is non-positive (%s); identity 1.0 fallback for %s→%s",
            from_code,
            usd_to_from.rate,
            from_code,
            to_code,
        )
        return RateResult(rate=1.0, source="fallback_identity", used_fallback=True)

    # Prefer the "worse" source label for transparency.
    source_priority = {
        "identity": 0,
        "cache": 1,
        "api": 1,
        "stale_cache": 2,
        "average": 3,
        "default": 4,
        "fallback_identity": 5,
    }
    source = usd_to_from.source
    if source_priority.get(usd_to_to.source, 0) > source_priority.get(source, 0):
        source = usd_to_to.source

    return RateResult(
        rate=usd_to_to.rate / usd_to_from.rate,
        source=source,
        used_fallback=False,
    )


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
    Unknown currencies return 1.0 with a warning (see ``get_rate_result``).
    """
    return get_rate_result(db, from_code, to_code, target_date).rate


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


def convert_currency_result(
    amount: float,
    from_currency: str,
    to_currency: str,
    db: Session,
    rate_date: Optional[date] = None,
) -> tuple[float, RateResult]:
    """Convert amount and return ``(converted_amount, RateResult)``.

    When ``RateResult.used_fallback`` is True the conversion used identity 1:1
    because no rate was available — do not treat that as a successful live quote.
    """
    if from_currency == to_currency:
        return amount, RateResult(rate=1.0, source="identity", used_fallback=False)
    meta = get_rate_result(db, from_currency, to_currency, rate_date)
    return amount * meta.rate, meta


def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
    db: Session,
    rate_date: Optional[date] = None,
) -> float:
    """Convert amount from from_currency to to_currency. Supports any pair."""
    converted, _meta = convert_currency_result(
        amount, from_currency, to_currency, db, rate_date=rate_date
    )
    return converted


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
            resp = _get_requests_session().get(url, timeout=timeout)
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
