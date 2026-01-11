"""
Currency service for multi-currency operations
"""
from backend.database import db
from backend.models import Currency


def get_all_currencies():
    """Get all currencies"""
    return Currency.query.all()


def get_currency_by_code(code):
    """Get currency by code (e.g., 'COP', 'USD')"""
    return Currency.query.filter_by(code=code).first()


def get_base_currency():
    """Get base currency (COP)"""
    return Currency.query.filter_by(is_base=True).first()


def update_exchange_rate(currency_code, new_rate):
    """Update exchange rate for a currency"""
    currency = get_currency_by_code(currency_code)
    if currency:
        currency.exchange_rate_to_base = new_rate
        db.session.commit()
        return currency
    return None


def convert_to_base(amount, from_currency_code):
    """
    Convert amount from any currency to base currency (COP)
    """
    if from_currency_code == 'COP':
        return amount

    currency = get_currency_by_code(from_currency_code)
    if currency:
        return amount * currency.exchange_rate_to_base
    return amount


def convert_currency(amount, from_currency_code, to_currency_code):
    """
    Convert amount from one currency to another
    """
    if from_currency_code == to_currency_code:
        return amount

    # Convert to base first, then to target currency
    base_amount = convert_to_base(amount, from_currency_code)

    if to_currency_code == 'COP':
        return base_amount

    to_currency = get_currency_by_code(to_currency_code)
    if to_currency and to_currency.exchange_rate_to_base > 0:
        return base_amount / to_currency.exchange_rate_to_base

    return amount


def format_currency(amount, currency_code):
    """
    Format amount with proper currency symbol and decimals
    """
    currency = get_currency_by_code(currency_code)
    if not currency:
        return f"{amount:,.2f}"

    if currency.decimals == 0:
        return f"{currency.symbol}{amount:,.0f}"
    else:
        return f"{currency.symbol}{amount:,.{currency.decimals}f}"
