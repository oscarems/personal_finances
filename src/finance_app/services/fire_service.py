from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from finance_app.models import Transaction, CategoryGroup, Category
from finance_app.models.investment_asset import InvestmentAsset
from finance_app.services.portfolio_service import _enrich_asset


def _get_gastos_anuales(db: Session) -> float:
    today = date.today()
    since = today - relativedelta(months=12)

    transactions = (
        db.query(Transaction)
        .join(Category, Transaction.category_id == Category.id, isouter=True)
        .join(CategoryGroup, Category.category_group_id == CategoryGroup.id, isouter=True)
        .filter(
            Transaction.date >= since,
            Transaction.date <= today,
            Transaction.amount < 0,
            Transaction.transfer_account_id.is_(None),
            Transaction.is_adjustment.is_(False),
        )
        .filter(CategoryGroup.is_income.is_(False))
        .all()
    )

    return sum(abs(t.amount) for t in transactions)


def _get_ingreso_pasivo(db: Session) -> float:
    assets = db.query(InvestmentAsset).filter(
        InvestmentAsset.activo == True,
    ).all()

    total = 0.0
    for asset in assets:
        rental_yield = getattr(asset, "rental_yield", None)
        if rental_yield and rental_yield > 0:
            enriched = _enrich_asset(db, asset)
            total += (rental_yield / 100) * enriched["valor_actual"]
    return total


def get_fire_dashboard(db: Session) -> dict:
    assets = db.query(InvestmentAsset).filter(
        InvestmentAsset.activo == True,
    ).all()

    patrimonio_invertible = sum(
        _enrich_asset(db, a)["valor_actual"] for a in assets
    )

    gastos_anuales = _get_gastos_anuales(db)
    ingreso_pasivo_anual = _get_ingreso_pasivo(db)

    fire_number = gastos_anuales * 25
    ratio_fire = (patrimonio_invertible / fire_number) if fire_number > 0 else 0.0
    independencia_pct = min(ratio_fire * 100, 100.0)

    ingreso_pasivo_vs_gastos_pct = (
        (ingreso_pasivo_anual / gastos_anuales * 100) if gastos_anuales > 0 else 0.0
    )

    anos_restantes = None
    if ratio_fire < 1.0 and gastos_anuales > 0 and ingreso_pasivo_anual < gastos_anuales:
        faltante = fire_number - patrimonio_invertible
        tasa_ahorro_anual = ingreso_pasivo_anual
        if tasa_ahorro_anual > 0:
            anos_restantes = round(faltante / tasa_ahorro_anual, 1)

    return {
        "patrimonio_invertible": round(patrimonio_invertible, 2),
        "gastos_anuales_esenciales": round(gastos_anuales, 2),
        "ingreso_pasivo_anual": round(ingreso_pasivo_anual, 2),
        "ratio_fire": round(ratio_fire, 4),
        "independencia_pct": round(independencia_pct, 2),
        "ingreso_pasivo_vs_gastos_pct": round(ingreso_pasivo_vs_gastos_pct, 2),
        "anos_restantes": anos_restantes,
    }
