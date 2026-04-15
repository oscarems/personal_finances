"""
Exchange Rate Service
Fetches USD-COP exchange rates from public APIs with intelligent fallback.
"""
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc
import requests
from typing import Optional

from finance_app.models import ExchangeRate
from finance_app.config import EXCHANGE_RATE_API

MIN_USD_COP_RATE = 100.0
MAX_USD_COP_RATE = 100000.0


def is_rate_plausible(rate: Optional[float]) -> bool:
    if rate is None:
        return False
    return MIN_USD_COP_RATE <= rate <= MAX_USD_COP_RATE


def fetch_rate_from_api(api_url: str, timeout: int = 5) -> Optional[float]:
    """
    Attempt to fetch the USD->COP exchange rate from a public API.

    Low-level helper that makes the actual HTTP request.
    Supports multiple response formats from different APIs.

    Args:
        api_url (str): Full API URL (e.g. 'https://api.exchangerate-api.com/v4/latest/USD').
        timeout (int): Seconds before timeout (default: 5).

    Returns:
        Optional[float]: USD->COP rate if successful, None on failure.

    Supported APIs:
        - exchangerate-api.com: format {"rates": {"COP": 3850.5}}
        - exchangerate.host: format {"rates": {"COP": 3850.5}}

    Error handling:
        - Connection timeout → None
        - Status code != 200 → None
        - Invalid JSON → None
        - Unexpected format → None

    Example:
        >>> rate = fetch_rate_from_api('https://api.exchangerate-api.com/v4/latest/USD')
        >>> print(rate)
        3850.5
    """
    try:
        response = requests.get(api_url, timeout=timeout)
        if response.status_code == 200:
            data = response.json()

            # Ambas APIs usan formato {"rates": {"COP": ...}}
            if 'rates' in data and 'COP' in data['rates']:
                return float(data['rates']['COP'])

            # Formato alternativo: {"conversion_rates": {"COP": ...}}
            if 'conversion_rates' in data and 'COP' in data['conversion_rates']:
                return float(data['conversion_rates']['COP'])

    except Exception as e:
        print(f"⚠️  Error fetching from {api_url}: {str(e)}")

    return None


def get_average_recent_rates(db: Session, days: int = 5) -> Optional[float]:
    """
    Calculate the average of the last N stored rates.
    """
    recent_rates = db.query(ExchangeRate).filter(
        ExchangeRate.from_currency == 'USD',
        ExchangeRate.to_currency == 'COP'
    ).order_by(desc(ExchangeRate.date)).limit(days).all()

    valid_rates = [r.rate for r in recent_rates if is_rate_plausible(r.rate)]

    if valid_rates:
        avg = sum(valid_rates) / len(valid_rates)
        print(f"📊 Using average of last {len(recent_rates)} rates: {avg:.2f}")
        return avg

    return None


def get_current_exchange_rate(db: Session, force_fetch: bool = False) -> float:
    """
    Get the current USD->COP exchange rate using a 5-level fallback strategy.

    Main function for obtaining exchange rates. Implements a robust fallback chain
    that ALWAYS returns a valid rate, even when public APIs are unavailable.

    5-LEVEL STRATEGY (in order):

        Level 1 - TODAY'S CACHE:
            Already fetched today? Use it (fast, no API calls).
            Skipped if force_fetch=True.

        Level 2 - PRIMARY API:
            Try exchangerate-api.com (2 attempts).
            On success → save to DB and return.

        Level 3 - FALLBACK API:
            Try exchangerate.host (2 attempts).
            On success → save to DB and return.

        Level 4 - HISTORICAL AVERAGE:
            Compute average of the last 5 rates in DB.
            If found → save as today's rate.

        Level 5 - DEFAULT RATE:
            Use configured default rate (4000 COP per USD).
            Last resort if everything else fails.

    Args:
        db (Session): Database session.
        force_fetch (bool): If True, ignore cache and force an API call.

    Returns:
        float: USD->COP exchange rate (always returns a valid value).

    Configuration:
        API URLs, timeouts and retries are set in config.py:
        EXCHANGE_RATE_API = {
            'primary': 'https://api.exchangerate-api.com/v4/latest/USD',
            'fallback': 'https://api.exchangerate.host/latest?base=USD',
            'timeout': 5,
            'retries': 2,
            'fallback_average_days': 5,
            'default_rate': 4000
        }

    Side effects:
        - Saves the successful rate to the exchange_rates table with a source tag.
        - Prints informational logs to stdout.

    Notes:
        - This function ALWAYS returns a value and never raises.
        - Cache the result if called multiple times within a single request.
    """
    config = EXCHANGE_RATE_API
    today = date.today()

    # 1. Verificar si ya tenemos tasa para hoy
    if not force_fetch:
        existing_rate = db.query(ExchangeRate).filter(
            ExchangeRate.date == today,
            ExchangeRate.from_currency == 'USD',
            ExchangeRate.to_currency == 'COP'
        ).first()

        if existing_rate and is_rate_plausible(existing_rate.rate):
            print(f"✓ Using today's rate from database: {existing_rate.rate}")
            return existing_rate.rate
        elif existing_rate:
            print(f"⚠️  Ignoring implausible rate stored for today: {existing_rate.rate}")

    # 2. Intentar API primaria
    print(f"🔄 Fetching rate from primary API...")
    for attempt in range(config['retries']):
        rate = fetch_rate_from_api(config['primary'], config['timeout'])
        if rate and is_rate_plausible(rate):
            # Guardar en base de datos
            exchange_rate = ExchangeRate(
                from_currency='USD',
                to_currency='COP',
                rate=rate,
                date=today,
                source='api_primary'
            )
            db.add(exchange_rate)
            db.commit()
            print(f"✓ Got rate from primary API: {rate}")
            return rate
        if rate:
            print(f"⚠️  Ignoring implausible rate from primary API: {rate}")
        print(f"  Attempt {attempt + 1} failed")

    # 3. Intentar API de respaldo
    print(f"🔄 Fetching rate from fallback API...")
    for attempt in range(config['retries']):
        rate = fetch_rate_from_api(config['fallback'], config['timeout'])
        if rate and is_rate_plausible(rate):
            exchange_rate = ExchangeRate(
                from_currency='USD',
                to_currency='COP',
                rate=rate,
                date=today,
                source='api_fallback'
            )
            db.add(exchange_rate)
            db.commit()
            print(f"✓ Got rate from fallback API: {rate}")
            return rate
        if rate:
            print(f"⚠️  Ignoring implausible rate from fallback API: {rate}")
        print(f"  Attempt {attempt + 1} failed")

    # 4. Usar promedio de últimos días
    print(f"⚠️  All APIs failed. Trying average of recent rates...")
    avg_rate = get_average_recent_rates(db, config['fallback_average_days'])
    if avg_rate and is_rate_plausible(avg_rate):
        # Guardar el promedio como tasa del día
        exchange_rate = ExchangeRate(
            from_currency='USD',
            to_currency='COP',
            rate=avg_rate,
            date=today,
            source='average'
        )
        db.add(exchange_rate)
        db.commit()
        return avg_rate

    # 5. Usar tasa por defecto
    print(f"⚠️  Using default rate: {config['default_rate']}")
    exchange_rate = ExchangeRate(
        from_currency='USD',
        to_currency='COP',
        rate=config['default_rate'],
        date=today,
        source='default'
    )
    db.add(exchange_rate)
    db.commit()
    return config['default_rate']


def get_rate_for_date(db: Session, target_date: date) -> float:
    """
    Get the exchange rate for a specific date.
    If not found, falls back to the nearest earlier rate.
    """
    # Buscar tasa exacta para esa fecha
    rate = db.query(ExchangeRate).filter(
        ExchangeRate.date == target_date,
        ExchangeRate.from_currency == 'USD',
        ExchangeRate.to_currency == 'COP'
    ).first()

    if rate and is_rate_plausible(rate.rate):
        return rate.rate
    elif rate:
        print(f"⚠️  Ignoring implausible historical rate for {target_date}: {rate.rate}")

    # Buscar la tasa más cercana anterior
    rate = db.query(ExchangeRate).filter(
        ExchangeRate.date < target_date,
        ExchangeRate.from_currency == 'USD',
        ExchangeRate.to_currency == 'COP'
    ).order_by(desc(ExchangeRate.date)).first()

    if rate and is_rate_plausible(rate.rate):
        return rate.rate
    elif rate:
        print(f"⚠️  Ignoring implausible historical rate before {target_date}: {rate.rate}")

    # Si no hay ninguna tasa histórica, obtener la actual
    return get_current_exchange_rate(db)


def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
    db: Session,
    rate_date: Optional[date] = None
) -> float:
    """
    Convert a monetary amount from one currency to another using the exchange rate.

    Main conversion function used throughout the system. Supports current or
    historical rate conversion, and short-circuits when source and target are the same.

    Args:
        amount (float): Amount to convert.
        from_currency (str): Source currency code ('USD' or 'COP').
        to_currency (str): Target currency code ('USD' or 'COP').
        db (Session): Database session (used to fetch the rate).
        rate_date (Optional[date]): Date for a historical rate; None = current rate.

    Returns:
        float: Converted amount in the target currency.

    Examples:
        # USD to COP (current rate)
        >>> convert_currency(100, 'USD', 'COP', db)
        400000.0

        # COP to USD (current rate)
        >>> convert_currency(400000, 'COP', 'USD', db)
        100.0

        # Same currency (returns amount unchanged)
        >>> convert_currency(100, 'USD', 'USD', db)
        100.0

        # Historical rate for January 1st
        >>> convert_currency(100, 'USD', 'COP', db, rate_date=date(2025, 1, 1))
        385000.0

    Formulas:
        USD → COP: amount * rate
        COP → USD: amount / rate

    Notes:
        - Currently only supports USD and COP.
        - Other currency pairs return the amount unchanged.
        - Internally calls get_current_exchange_rate() or get_rate_for_date().
    """
    if from_currency == to_currency:
        return amount

    # Obtener tasa (actual o histórica)
    if rate_date:
        rate = get_rate_for_date(db, rate_date)
    else:
        rate = get_current_exchange_rate(db)

    # Convertir
    if from_currency == 'USD' and to_currency == 'COP':
        return amount * rate
    elif from_currency == 'COP' and to_currency == 'USD':
        if rate <= 0:
            return amount
        return amount / rate

    return amount
