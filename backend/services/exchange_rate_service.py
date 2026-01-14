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
    Intenta obtener la tasa de cambio USD->COP desde una API pública.

    Esta función es el helper de bajo nivel que hace la petición HTTP real.
    Soporta múltiples formatos de respuesta de diferentes APIs.

    Args:
        api_url (str): URL completa de la API (ej: 'https://api.exchangerate-api.com/v4/latest/USD')
        timeout (int): Segundos antes de timeout (default: 5)

    Returns:
        Optional[float]: Tasa USD->COP si exitoso, None si falla

    APIs soportadas:
        - exchangerate-api.com: formato {"rates": {"COP": 3850.5}}
        - exchangerate.host: formato {"rates": {"COP": 3850.5}}

    Manejo de errores:
        - Timeout de conexión → None
        - Status code != 200 → None
        - JSON inválido → None
        - Formato inesperado → None

    Ejemplo:
        >>> rate = fetch_rate_from_api('https://api.exchangerate-api.com/v4/latest/USD')
        >>> print(rate)
        3850.5
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
    Obtiene la tasa de cambio actual USD->COP con sistema de fallback inteligente de 5 niveles.

    Esta es la función principal para obtener tasas de cambio. Implementa un sistema
    robusto de fallbacks para garantizar que SIEMPRE retorna una tasa válida, incluso
    si las APIs públicas están caídas.

    ESTRATEGIA DE 5 NIVELES (en orden):

        Nivel 1 - CACHÉ DE HOY:
            ¿Ya obtuvimos la tasa hoy? → Usarla (rápido, sin API calls)
            Saltado si force_fetch=True

        Nivel 2 - API PRIMARIA:
            Intentar obtener de exchangerate-api.com (2 intentos)
            Si exitoso → Guardar en DB y retornar

        Nivel 3 - API FALLBACK:
            Intentar obtener de exchangerate.host (2 intentos)
            Si exitoso → Guardar en DB y retornar

        Nivel 4 - PROMEDIO HISTÓRICO:
            Calcular promedio de últimas 5 tasas en DB
            Si existen → Guardar promedio como tasa de hoy

        Nivel 5 - TASA POR DEFECTO:
            Usar tasa configurada (4000 COP por USD)
            Última opción si todo lo demás falla

    Args:
        db (Session): Sesión de base de datos
        force_fetch (bool): Si True, ignora caché y fuerza consulta a API

    Returns:
        float: Tasa de cambio USD->COP (siempre retorna un valor válido)

    Ejemplos:
        # Uso normal (usa caché si existe)
        >>> rate = get_current_exchange_rate(db)
        ✓ Using today's rate from database: 3850.5
        >>> print(rate)
        3850.5

        # Forzar actualización desde API
        >>> rate = get_current_exchange_rate(db, force_fetch=True)
        🔄 Fetching rate from primary API...
        ✓ Got rate from primary API: 3852.0

        # Cuando todo falla
        >>> rate = get_current_exchange_rate(db)
        ⚠️ All APIs failed. Trying average of recent rates...
        📊 Using average of last 5 rates: 3848.20

    Configuración:
        Las URLs de las APIs, timeouts y reintentos se configuran en config.py:
        EXCHANGE_RATE_API = {
            'primary': 'https://api.exchangerate-api.com/v4/latest/USD',
            'fallback': 'https://api.exchangerate.host/latest?base=USD',
            'timeout': 5,
            'retries': 2,
            'fallback_average_days': 5,
            'default_rate': 4000
        }

    Efectos secundarios:
        - Guarda la tasa exitosa en la tabla exchange_rates con source
        - Imprime logs informativos en consola

    Notas:
        - Esta función SIEMPRE retorna un valor, nunca falla
        - Útil cachear el resultado si se llama múltiples veces en una request
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
    Convierte una cantidad de dinero de una moneda a otra usando tasa de cambio.

    Esta es la función principal de conversión usada en todo el sistema. Soporta
    conversión con tasa actual o histórica, y es inteligente para evitar conversiones
    innecesarias cuando origen y destino son iguales.

    Args:
        amount (float): Cantidad a convertir
        from_currency (str): Código de moneda origen ('USD' o 'COP')
        to_currency (str): Código de moneda destino ('USD' o 'COP')
        db (Session): Sesión de base de datos (para obtener tasa)
        rate_date (Optional[date]): Fecha para usar tasa histórica, None = tasa actual

    Returns:
        float: Cantidad convertida en la moneda destino

    Ejemplos:
        # Convertir USD a COP (tasa actual)
        >>> convert_currency(100, 'USD', 'COP', db)
        400000.0

        # Convertir COP a USD (tasa actual)
        >>> convert_currency(400000, 'COP', 'USD', db)
        100.0

        # Misma moneda (retorna igual sin hacer nada)
        >>> convert_currency(100, 'USD', 'USD', db)
        100.0

        # Usar tasa histórica del 1 de enero
        >>> convert_currency(100, 'USD', 'COP', db, rate_date=date(2025, 1, 1))
        385000.0  # Usa la tasa de ese día

    Fórmulas:
        USD → COP: monto * tasa
        COP → USD: monto / tasa

    Optimización:
        Si from_currency == to_currency, retorna amount inmediatamente sin queries

    Notas:
        - Actualmente solo soporta USD y COP
        - Para otras combinaciones retorna el monto sin cambios
        - Usa get_current_exchange_rate() o get_rate_for_date() internamente
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
