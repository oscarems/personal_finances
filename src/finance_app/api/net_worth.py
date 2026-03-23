"""
API de Patrimonio Neto (Net Worth)

Endpoints para consultar el patrimonio neto en una fecha puntual,
a lo largo del tiempo, y con proyecciones futuras.

Todos los montos se expresan en la moneda seleccionada (por defecto COP).
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models import Currency
from finance_app.services.wealth.net_worth_service import (
    build_net_worth_timeline,
    compute_net_worth_at_date,
    snapshot_to_dict,
    timeline_to_dict,
)

router = APIRouter()


@router.get("/snapshot")
def get_net_worth_snapshot(
    target_date: Optional[str] = None,
    currency_id: int = 1,
    include_accounts: bool = True,
    include_details: bool = False,
    db: Session = Depends(get_db),
):
    """
    Patrimonio neto en una fecha puntual.

    Calcula activos, pasivos y patrimonio neto para una fecha específica.
    Si no se indica fecha, usa la fecha actual.

    Parámetros:
        target_date: Fecha en formato ISO (YYYY-MM-DD). Default: hoy.
        currency_id: Moneda objetivo (1=COP, 2=USD). Default: COP.
        include_accounts: Incluir saldos de cuentas bancarias. Default: True.
        include_details: Incluir desglose individual de activos/pasivos. Default: False.
    """
    if target_date:
        parsed_date = date.fromisoformat(target_date)
    else:
        parsed_date = date.today()

    snapshot = compute_net_worth_at_date(
        db=db,
        target_date=parsed_date,
        currency_id=currency_id,
        include_accounts=include_accounts,
        include_details=include_details,
    )

    currency = db.query(Currency).get(currency_id)
    result = snapshot_to_dict(snapshot)
    result["currency"] = currency.to_dict() if currency else None
    return result


@router.get("/timeline")
def get_net_worth_timeline(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currency_id: int = 1,
    include_accounts: bool = False,
    projection_months: int = Query(0, ge=0, le=60),
    db: Session = Depends(get_db),
):
    """
    Patrimonio neto mensual a lo largo del tiempo.

    Genera una línea de tiempo mensual con activos, pasivos y patrimonio neto.
    Opcionalmente incluye meses de proyección hacia el futuro.

    Parámetros:
        start_date: Fecha inicio (ISO). Default: enero 2026.
        end_date: Fecha fin (ISO). Default: hoy.
        currency_id: Moneda objetivo. Default: COP.
        include_accounts: Incluir saldos de cuentas bancarias. Default: False.
        projection_months: Meses de proyección futura (0-60). Default: 0.
    """
    # Valores por defecto
    start = date.fromisoformat(start_date) if start_date else date(2026, 1, 1)
    end = date.fromisoformat(end_date) if end_date else date.today()

    timeline = build_net_worth_timeline(
        db=db,
        start_date=start,
        end_date=end,
        currency_id=currency_id,
        include_accounts=include_accounts,
        include_projection_months=projection_months,
    )

    currency = db.query(Currency).get(currency_id)
    return timeline_to_dict(timeline, currency)


@router.get("/compare")
def compare_net_worth_periods(
    date_a: str = Query(..., description="Primera fecha (ISO)"),
    date_b: str = Query(..., description="Segunda fecha (ISO)"),
    currency_id: int = 1,
    include_accounts: bool = True,
    db: Session = Depends(get_db),
):
    """
    Compara el patrimonio neto entre dos fechas.

    Útil para ver cuánto creció o disminuyó el patrimonio entre
    dos momentos en el tiempo.

    Parámetros:
        date_a: Primera fecha de comparación (ISO).
        date_b: Segunda fecha de comparación (ISO).
        currency_id: Moneda objetivo. Default: COP.
        include_accounts: Incluir saldos de cuentas. Default: True.
    """
    parsed_a = date.fromisoformat(date_a)
    parsed_b = date.fromisoformat(date_b)

    snapshot_a = compute_net_worth_at_date(
        db=db,
        target_date=parsed_a,
        currency_id=currency_id,
        include_accounts=include_accounts,
        include_details=True,
    )
    snapshot_b = compute_net_worth_at_date(
        db=db,
        target_date=parsed_b,
        currency_id=currency_id,
        include_accounts=include_accounts,
        include_details=True,
    )

    # Calcular diferencias por categoría
    all_categories = set(snapshot_a.assets_by_category.keys()) | set(snapshot_b.assets_by_category.keys())
    category_changes = {}
    for cat in all_categories:
        val_a = snapshot_a.assets_by_category.get(cat, 0.0)
        val_b = snapshot_b.assets_by_category.get(cat, 0.0)
        category_changes[cat] = {
            "date_a": round(val_a, 2),
            "date_b": round(val_b, 2),
            "change": round(val_b - val_a, 2),
            "change_percentage": round(((val_b - val_a) / val_a * 100) if val_a != 0 else 0, 2),
        }

    change = snapshot_b.net_worth - snapshot_a.net_worth
    change_pct = (change / snapshot_a.net_worth * 100) if snapshot_a.net_worth != 0 else 0

    currency = db.query(Currency).get(currency_id)

    return {
        "date_a": snapshot_to_dict(snapshot_a),
        "date_b": snapshot_to_dict(snapshot_b),
        "change": round(change, 2),
        "change_percentage": round(change_pct, 2),
        "assets_change": round(snapshot_b.total_assets - snapshot_a.total_assets, 2),
        "liabilities_change": round(snapshot_b.total_liabilities - snapshot_a.total_liabilities, 2),
        "category_changes": category_changes,
        "currency": currency.to_dict() if currency else None,
    }
