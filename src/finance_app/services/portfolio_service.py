from __future__ import annotations

import json
from datetime import date

from sqlalchemy.orm import Session

from finance_app.models.investment_portfolio import InvestmentPortfolio
from finance_app.models.investment_asset import InvestmentAsset
from finance_app.models.asset_price_history import AssetPriceHistory


def get_asset_current_price(db: Session, asset_id: int) -> float | None:
    record = (
        db.query(AssetPriceHistory)
        .filter(AssetPriceHistory.asset_id == asset_id)
        .order_by(AssetPriceHistory.fecha.desc())
        .first()
    )
    return record.precio if record else None


def _enrich_asset(db: Session, asset: InvestmentAsset) -> dict:
    precio_actual = get_asset_current_price(db, asset.id)
    if precio_actual is None:
        precio_actual = asset.precio_compra

    valor_actual = asset.unidades * precio_actual
    costo_base = asset.unidades * asset.precio_compra
    ganancia = valor_actual - costo_base
    ganancia_pct = (ganancia / costo_base * 100) if costo_base != 0 else 0.0

    return {
        "id": asset.id,
        "portfolio_id": asset.portfolio_id,
        "simbolo": asset.simbolo,
        "nombre": asset.nombre,
        "tipo": asset.tipo,
        "asset_class": asset.asset_class,
        "unidades": asset.unidades,
        "precio_compra": asset.precio_compra,
        "fecha_compra": asset.fecha_compra.isoformat() if asset.fecha_compra else None,
        "moneda": asset.moneda,
        "notas": asset.notas,
        "activo": asset.activo,
        "precio_actual": precio_actual,
        "valor_actual": round(valor_actual, 2),
        "costo_base": round(costo_base, 2),
        "ganancia": round(ganancia, 2),
        "ganancia_pct": round(ganancia_pct, 2),
    }


def get_all_portfolios(db: Session) -> list[dict]:
    portfolios = db.query(InvestmentPortfolio).all()
    result = []
    for p in portfolios:
        assets = db.query(InvestmentAsset).filter(
            InvestmentAsset.portfolio_id == p.id,
            InvestmentAsset.activo == True,
        ).all()

        valor_total = 0.0
        costo_base = 0.0
        for asset in assets:
            enriched = _enrich_asset(db, asset)
            valor_total += enriched["valor_actual"]
            costo_base += enriched["costo_base"]

        ganancia = valor_total - costo_base
        ganancia_pct = (ganancia / costo_base * 100) if costo_base != 0 else 0.0

        target_allocation = None
        if p.target_allocation:
            try:
                target_allocation = json.loads(p.target_allocation)
            except (ValueError, TypeError):
                target_allocation = None

        result.append({
            "id": p.id,
            "nombre": p.nombre,
            "descripcion": p.descripcion,
            "target_allocation": target_allocation,
            "moneda": p.moneda,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "valor_total": round(valor_total, 2),
            "costo_base": round(costo_base, 2),
            "ganancia": round(ganancia, 2),
            "ganancia_pct": round(ganancia_pct, 2),
            "num_assets": len(assets),
        })
    return result


def get_portfolio_detail(db: Session, portfolio_id: int) -> dict:
    portfolio = db.query(InvestmentPortfolio).filter(
        InvestmentPortfolio.id == portfolio_id
    ).first()
    if not portfolio:
        return {}

    assets = db.query(InvestmentAsset).filter(
        InvestmentAsset.portfolio_id == portfolio_id,
        InvestmentAsset.activo == True,
    ).all()

    enriched_assets = [_enrich_asset(db, a) for a in assets]

    valor_total = sum(a["valor_actual"] for a in enriched_assets)
    costo_base = sum(a["costo_base"] for a in enriched_assets)
    ganancia = valor_total - costo_base
    ganancia_pct = (ganancia / costo_base * 100) if costo_base != 0 else 0.0

    target_allocation = None
    if portfolio.target_allocation:
        try:
            target_allocation = json.loads(portfolio.target_allocation)
        except (ValueError, TypeError):
            target_allocation = None

    return {
        "id": portfolio.id,
        "nombre": portfolio.nombre,
        "descripcion": portfolio.descripcion,
        "target_allocation": target_allocation,
        "moneda": portfolio.moneda,
        "created_at": portfolio.created_at.isoformat() if portfolio.created_at else None,
        "valor_total": round(valor_total, 2),
        "costo_base": round(costo_base, 2),
        "ganancia": round(ganancia, 2),
        "ganancia_pct": round(ganancia_pct, 2),
        "assets": enriched_assets,
    }


def create_portfolio(
    db: Session,
    nombre: str,
    descripcion: str,
    target_allocation: dict,
    moneda: str,
) -> dict:
    portfolio = InvestmentPortfolio(
        nombre=nombre,
        descripcion=descripcion,
        target_allocation=json.dumps(target_allocation) if target_allocation else None,
        moneda=moneda,
    )
    db.add(portfolio)
    db.commit()
    db.refresh(portfolio)

    return {
        "id": portfolio.id,
        "nombre": portfolio.nombre,
        "descripcion": portfolio.descripcion,
        "target_allocation": target_allocation,
        "moneda": portfolio.moneda,
        "created_at": portfolio.created_at.isoformat() if portfolio.created_at else None,
    }


def create_asset(
    db: Session,
    portfolio_id: int | None,
    simbolo: str,
    nombre: str,
    tipo: str,
    asset_class: str,
    unidades: float,
    precio_compra: float,
    fecha_compra: str,
    moneda: str,
    notas: str | None = None,
) -> dict:
    from datetime import date as date_type
    fecha = date_type.fromisoformat(fecha_compra) if isinstance(fecha_compra, str) else fecha_compra

    asset = InvestmentAsset(
        portfolio_id=portfolio_id,
        simbolo=simbolo,
        nombre=nombre,
        tipo=tipo,
        asset_class=asset_class,
        unidades=unidades,
        precio_compra=precio_compra,
        fecha_compra=fecha,
        moneda=moneda,
        notas=notas,
        activo=True,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _enrich_asset(db, asset)


def get_portfolio_allocation(db: Session, portfolio_id: int) -> dict:
    assets = db.query(InvestmentAsset).filter(
        InvestmentAsset.portfolio_id == portfolio_id,
        InvestmentAsset.activo == True,
    ).all()

    if not assets:
        return {}

    totals_by_class: dict[str, float] = {}
    grand_total = 0.0

    for asset in assets:
        enriched = _enrich_asset(db, asset)
        cls = asset.asset_class
        totals_by_class[cls] = totals_by_class.get(cls, 0.0) + enriched["valor_actual"]
        grand_total += enriched["valor_actual"]

    if grand_total == 0:
        return {cls: 0.0 for cls in totals_by_class}

    return {
        cls: round(val / grand_total * 100, 2)
        for cls, val in totals_by_class.items()
    }
