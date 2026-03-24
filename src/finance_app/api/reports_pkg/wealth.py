"""
Net worth and real estate wealth report endpoints.
"""
from typing import Optional
from datetime import date
from dateutil.relativedelta import relativedelta

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models import Currency
from finance_app.services.wealth.real_estate_service import build_real_estate_wealth_timeline

from .common import get_exchange_rate

router = APIRouter()


@router.get("/net-worth")
def get_net_worth(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """Calcula el patrimonio neto (Activos - Pasivos) a lo largo del tiempo."""
    from finance_app.services.wealth.net_worth_service import (
        build_net_worth_timeline,
        snapshot_to_dict,
        timeline_to_dict,
    )

    if not start_date:
        start_date = '2026-01-01'
    if not end_date:
        end_date = date.today().isoformat()

    start_date_obj = date.fromisoformat(start_date)
    end_date_obj = date.fromisoformat(end_date)

    timeline = build_net_worth_timeline(
        db=db,
        start_date=start_date_obj,
        end_date=end_date_obj,
        currency_id=currency_id,
        include_accounts=False,
    )

    currency = db.query(Currency).get(currency_id)
    return timeline_to_dict(timeline, currency)


@router.get("/real-estate-wealth")
def get_real_estate_wealth(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    projection_months: int = Query(12, ge=0, le=36),
    currency_id: int = 1,
    db: Session = Depends(get_db),
):
    today = date.today()
    if not end_date:
        end_date = today.isoformat()
    if not start_date:
        start_date = (today.replace(day=1) - relativedelta(months=11)).isoformat()

    start_date_obj = date.fromisoformat(start_date)
    end_date_obj = date.fromisoformat(end_date)

    if start_date_obj > end_date_obj:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    try:
        return build_real_estate_wealth_timeline(
            db=db,
            start_date=start_date_obj,
            end_date=end_date_obj,
            projection_months=projection_months,
            currency_id=currency_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
