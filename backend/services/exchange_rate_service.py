"""
Exchange Rate Service
Obtiene tasas de cambio USD-COP desde APIs públicas con fallback inteligente
"""
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc
import requests
from typing import Optional

from backend.models import ExchangeRate
from config import EXCHANGE_RATE_API


def fetch_rate_from_api(api_url: str, timeout: int = 5) -> Optional[float]:
    """
    Intenta obtener la tasa desde una API específica
    Returns: tasa USD->COP o None si falla
    """
    try:
        response = requests.get(api_url, timeout=timeout)
        if response.status_code == 200:
            data = response.json()

            # Diferentes APIs tienen diferentes estructuras
            # API 1: exchangerate-api.com
            if 'rates' in data and 'COP' in data['rates']:
                return float(data['rates']['COP'])

            # API 2: exchangerate.host
            if 'rates' in data and 'COP' in data['rates']:
                return float(data['rates']['COP'])

    except Exception as e:
        print(f"⚠️  Error fetching from {api_url}: {str(e)}")

    return None


def get_average_recent_rates(db: Session, days: int = 5) -> Optional[float]:
    """
    Calcula el promedio de las últimas N tasas guardadas
    """
    recent_rates = db.query(ExchangeRate).filter(
        ExchangeRate.from_currency == 'USD',
        ExchangeRate.to_currency == 'COP'
    ).order_by(desc(ExchangeRate.date)).limit(days).all()

    if recent_rates:
        avg = sum(r.rate for r in recent_rates) / len(recent_rates)
        print(f"📊 Using average of last {len(recent_rates)} rates: {avg:.2f}")
        return avg

    return None


def get_current_exchange_rate(db: Session, force_fetch: bool = False) -> float:
    """
    Obtiene la tasa de cambio actual USD->COP con fallback inteligente:

    1. Si ya existe tasa para hoy en DB, usar esa (a menos que force_fetch=True)
    2. Intentar API primaria (2 intentos)
    3. Intentar API de respaldo (2 intentos)
    4. Usar promedio de últimos 5 días
    5. Usar tasa por defecto (3800)

    Returns: tasa USD->COP
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

        if existing_rate:
            print(f"✓ Using today's rate from database: {existing_rate.rate}")
            return existing_rate.rate

    # 2. Intentar API primaria
    print(f"🔄 Fetching rate from primary API...")
    for attempt in range(config['retries']):
        rate = fetch_rate_from_api(config['primary'], config['timeout'])
        if rate:
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
        print(f"  Attempt {attempt + 1} failed")

    # 3. Intentar API de respaldo
    print(f"🔄 Fetching rate from fallback API...")
    for attempt in range(config['retries']):
        rate = fetch_rate_from_api(config['fallback'], config['timeout'])
        if rate:
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
        print(f"  Attempt {attempt + 1} failed")

    # 4. Usar promedio de últimos días
    print(f"⚠️  All APIs failed. Trying average of recent rates...")
    avg_rate = get_average_recent_rates(db, config['fallback_average_days'])
    if avg_rate:
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
    Obtiene la tasa de cambio para una fecha específica
    Si no existe, busca la más cercana anterior
    """
    # Buscar tasa exacta para esa fecha
    rate = db.query(ExchangeRate).filter(
        ExchangeRate.date == target_date,
        ExchangeRate.from_currency == 'USD',
        ExchangeRate.to_currency == 'COP'
    ).first()

    if rate:
        return rate.rate

    # Buscar la tasa más cercana anterior
    rate = db.query(ExchangeRate).filter(
        ExchangeRate.date < target_date,
        ExchangeRate.from_currency == 'USD',
        ExchangeRate.to_currency == 'COP'
    ).order_by(desc(ExchangeRate.date)).first()

    if rate:
        return rate.rate

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
    Convierte un monto de una moneda a otra
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
        return amount / rate

    return amount
