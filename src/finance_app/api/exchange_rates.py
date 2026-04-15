"""
Exchange Rates API
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from datetime import date, timedelta

from finance_app.database import get_db
from finance_app.models import ExchangeRate
from finance_app.services.exchange_rate_service import (
    get_current_exchange_rate,
    convert_currency
)

router = APIRouter()


@router.get("/current")
def get_current_rate(
    force_fetch: bool = False,
    db: Session = Depends(get_db)
):
    """
    Get the current USD->COP exchange rate.
    force_fetch: force an API query even if today's rate already exists.
    """
    rate = get_current_exchange_rate(db, force_fetch=force_fetch)

    # Return the actual date of the rate record so the UI can show staleness
    latest_record = db.query(ExchangeRate).filter(
        ExchangeRate.from_currency == 'USD',
        ExchangeRate.to_currency == 'COP'
    ).order_by(desc(ExchangeRate.date)).first()

    rate_date = latest_record.date if latest_record else date.today()
    source = latest_record.source if latest_record else "unknown"
    days_old = (date.today() - rate_date).days if rate_date else 0

    return {
        "from_currency": "USD",
        "to_currency": "COP",
        "rate": rate,
        "date": rate_date.isoformat(),
        "source": source,
        "days_old": days_old,
    }


@router.get("/history")
def get_rate_history(
    days: int = Query(default=30, le=365),
    db: Session = Depends(get_db)
):
    """
    Get the exchange rate history.
    """
    start_date = date.today() - timedelta(days=days)

    rates = db.query(ExchangeRate).filter(
        ExchangeRate.date >= start_date,
        ExchangeRate.from_currency == 'USD',
        ExchangeRate.to_currency == 'COP'
    ).order_by(desc(ExchangeRate.date)).all()

    return {
        "rates": [r.to_dict() for r in rates],
        "count": len(rates)
    }


@router.get("/convert")
def convert(
    amount: float,
    from_currency: str,
    to_currency: str,
    rate_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Convert an amount from one currency to another.
    """
    target_date = date.fromisoformat(rate_date) if rate_date else None

    converted = convert_currency(
        amount=amount,
        from_currency=from_currency,
        to_currency=to_currency,
        db=db,
        rate_date=target_date
    )

    return {
        "amount": amount,
        "from_currency": from_currency,
        "to_currency": to_currency,
        "converted_amount": converted,
        "date": target_date.isoformat() if target_date else date.today().isoformat()
    }
