from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from finance_app.models.investment_asset import InvestmentAsset
from finance_app.models.asset_price_history import AssetPriceHistory


def add_price(
    db: Session,
    asset_id: int,
    fecha: str,
    precio: float,
    fuente: str = "manual",
) -> dict:
    fecha_date = date.fromisoformat(fecha) if isinstance(fecha, str) else fecha

    record = db.query(AssetPriceHistory).filter(
        AssetPriceHistory.asset_id == asset_id,
        AssetPriceHistory.fecha == fecha_date,
    ).first()

    if record:
        record.precio = precio
        record.fuente = fuente
    else:
        record = AssetPriceHistory(
            asset_id=asset_id,
            fecha=fecha_date,
            precio=precio,
            fuente=fuente,
        )
        db.add(record)

    db.commit()
    db.refresh(record)
    return _price_to_dict(record)


def get_price_history(db: Session, asset_id: int, limit: int = 24) -> list[dict]:
    records = (
        db.query(AssetPriceHistory)
        .filter(AssetPriceHistory.asset_id == asset_id)
        .order_by(AssetPriceHistory.fecha.desc())
        .limit(limit)
        .all()
    )
    return [_price_to_dict(r) for r in records]


def get_latest_price(db: Session, asset_id: int) -> dict | None:
    record = (
        db.query(AssetPriceHistory)
        .filter(AssetPriceHistory.asset_id == asset_id)
        .order_by(AssetPriceHistory.fecha.desc())
        .first()
    )
    return _price_to_dict(record) if record else None


def get_all_assets_summary(db: Session) -> list[dict]:
    assets = db.query(InvestmentAsset).filter(
        InvestmentAsset.activo == True,
    ).all()

    result = []
    for asset in assets:
        latest = get_latest_price(db, asset.id)
        precio_actual = latest["precio"] if latest else asset.precio_compra

        valor_actual = asset.unidades * precio_actual
        costo_base = asset.unidades * asset.precio_compra
        ganancia = valor_actual - costo_base
        ganancia_pct = (ganancia / costo_base * 100) if costo_base != 0 else 0.0

        result.append({
            "id": asset.id,
            "simbolo": asset.simbolo,
            "nombre": asset.nombre,
            "tipo": asset.tipo,
            "asset_class": asset.asset_class,
            "unidades": asset.unidades,
            "precio_compra": asset.precio_compra,
            "precio_actual": precio_actual,
            "valor_actual": round(valor_actual, 2),
            "ganancia": round(ganancia, 2),
            "ganancia_pct": round(ganancia_pct, 2),
            "moneda": asset.moneda,
        })

    return result


def _price_to_dict(record: AssetPriceHistory) -> dict:
    return {
        "id": record.id,
        "asset_id": record.asset_id,
        "fecha": record.fecha.isoformat() if record.fecha else None,
        "precio": record.precio,
        "fuente": record.fuente,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }
