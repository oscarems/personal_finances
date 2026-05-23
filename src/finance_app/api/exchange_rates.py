"""
Exchange Rates API — multi-currency support.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from datetime import date, timedelta

from finance_app.database import get_db
from finance_app.models import ExchangeRate, Currency
from finance_app.services.exchange_rate_service import (
    get_rate,
    get_current_exchange_rate,
    convert_currency,
    sync_all_currency_rates,
    import_historical_rates,
    import_historical_rates_for_transactions,
)

router = APIRouter()


@router.get("/current")
def get_current_rate(
    from_currency: str = "USD",
    to_currency: str = "COP",
    force_fetch: bool = False,
    db: Session = Depends(get_db),
):
    """Get the current exchange rate for a currency pair."""
    if force_fetch:
        sync_all_currency_rates(db, force=True)

    rate = get_rate(db, from_currency.upper(), to_currency.upper())

    latest = (
        db.query(ExchangeRate)
        .filter_by(from_currency="USD", to_currency=to_currency.upper())
        .order_by(desc(ExchangeRate.date))
        .first()
    )

    rate_date = latest.date if latest else date.today()
    source = latest.source if latest else "unknown"
    days_old = (date.today() - rate_date).days

    return {
        "from_currency": from_currency.upper(),
        "to_currency": to_currency.upper(),
        "rate": rate,
        "date": rate_date.isoformat(),
        "source": source,
        "days_old": days_old,
    }


@router.get("/all")
def get_all_current_rates(db: Session = Depends(get_db)):
    """Get today's rates for all currencies relative to the base currency."""
    currencies = db.query(Currency).all()
    base = next((c for c in currencies if c.is_base), None)
    if not base:
        return {"rates": [], "base_currency": None}

    result = []
    for c in currencies:
        if c.code == base.code:
            result.append({"currency": c.to_dict(), "rate": 1.0, "source": "base"})
            continue
        r = get_rate(db, base.code, c.code)
        latest = (
            db.query(ExchangeRate)
            .filter_by(from_currency="USD", to_currency=c.code)
            .order_by(desc(ExchangeRate.date))
            .first()
        )
        result.append({
            "currency": c.to_dict(),
            "rate": r,
            "source": latest.source if latest else "unknown",
            "date": latest.date.isoformat() if latest else None,
        })

    return {"rates": result, "base_currency": base.to_dict()}


@router.get("/history")
def get_rate_history(
    from_currency: str = "USD",
    to_currency: str = "COP",
    days: int = Query(default=30, le=365),
    db: Session = Depends(get_db),
):
    """Get exchange rate history for a currency pair."""
    start_date = date.today() - timedelta(days=days)

    rates = (
        db.query(ExchangeRate)
        .filter(
            ExchangeRate.date >= start_date,
            ExchangeRate.from_currency == from_currency.upper(),
            ExchangeRate.to_currency == to_currency.upper(),
        )
        .order_by(desc(ExchangeRate.date))
        .all()
    )

    return {"rates": [r.to_dict() for r in rates], "count": len(rates)}


@router.get("/convert")
def convert(
    amount: float,
    from_currency: str,
    to_currency: str,
    rate_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Convert an amount between any two supported currencies."""
    target_date = date.fromisoformat(rate_date) if rate_date else None
    converted = convert_currency(
        amount=amount,
        from_currency=from_currency.upper(),
        to_currency=to_currency.upper(),
        db=db,
        rate_date=target_date,
    )
    return {
        "amount": amount,
        "from_currency": from_currency.upper(),
        "to_currency": to_currency.upper(),
        "converted_amount": converted,
        "date": target_date.isoformat() if target_date else date.today().isoformat(),
    }


@router.post("/sync")
def force_sync(db: Session = Depends(get_db)):
    """Force a re-fetch of all currency rates from the API."""
    sync_all_currency_rates(db, force=True)
    return {"ok": True, "message": "Tasas actualizadas desde la API."}


@router.get("/import-historical")
@router.post("/import-historical")
def import_historical(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Import historical USD→COP (and other currencies) rates for a date range.

    If no dates provided, imports only for dates that have transactions but
    no stored rate (smart mode — recommended for first-time setup).
    """
    if from_date and to_date:
        start = date.fromisoformat(from_date)
        end = date.fromisoformat(to_date)
        result = import_historical_rates(db, start, end)
    else:
        result = import_historical_rates_for_transactions(db)

    return {"ok": True, **result}
