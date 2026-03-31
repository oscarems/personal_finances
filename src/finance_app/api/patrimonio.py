"""Patrimonio API router: assets + net worth (debts come from Debt model)."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models.patrimonio_asset import PatrimonioAsset
from finance_app.models.debt import Debt
from finance_app.services.patrimonio.calculator import (
    calcular_valor_activo_en_mes,
    saldo_deuda_en_mes,
    calcular_patrimonio_en_mes,
    timeline_patrimonio,
)

router = APIRouter()

# Debt types included in patrimonio (excludes credit cards)
_PATRIMONIO_DEBT_TYPES = ("mortgage", "credit_loan")


# ── Pydantic schemas ─────────────────────────────────────────────────


class AssetCreate(BaseModel):
    nombre: str
    tipo: str  # inmueble, vehiculo, otro
    valor_adquisicion: float
    fecha_adquisicion: date
    tasa_anual: float = 0.0
    depreciation_method: Optional[str] = "sin_depreciacion"
    depreciation_rate: Optional[float] = None
    depreciation_years: Optional[int] = None
    depreciation_salvage_value: Optional[float] = None
    depreciation_start_date: Optional[date] = None
    return_rate: Optional[float] = None
    return_amount: Optional[float] = None
    moneda_id: int = 1
    notas: Optional[str] = None
    is_active: bool = True


class AssetUpdate(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    valor_adquisicion: Optional[float] = None
    fecha_adquisicion: Optional[date] = None
    tasa_anual: Optional[float] = None
    depreciation_method: Optional[str] = None
    depreciation_rate: Optional[float] = None
    depreciation_years: Optional[int] = None
    depreciation_salvage_value: Optional[float] = None
    depreciation_start_date: Optional[date] = None
    return_rate: Optional[float] = None
    return_amount: Optional[float] = None
    moneda_id: Optional[int] = None
    notas: Optional[str] = None
    is_active: Optional[bool] = None


# ── Helpers ──────────────────────────────────────────────────────────


def _get_patrimonio_debts(db: Session):
    """Get active debts that belong to patrimonio (not credit cards)."""
    return db.query(Debt).filter(
        Debt.is_active == True,
        Debt.debt_type.in_(_PATRIMONIO_DEBT_TYPES),
    ).all()


def _debt_term_months(debt: Debt) -> int:
    if debt.term_months:
        return int(debt.term_months)
    if debt.loan_years:
        return int(debt.loan_years) * 12
    return 0


def _debt_annual_rate(debt: Debt) -> float:
    """Return annual rate as a decimal (e.g. 0.115 for 11.5%)."""
    rate = float(debt.interest_rate or debt.annual_interest_rate or 0)
    return rate / 100 if rate > 1 else rate


# ── Summary / Timeline ──────────────────────────────────────────────


@router.get("/resumen")
def patrimonio_resumen(
    año: int = Query(default=None),
    mes: int = Query(default=None),
    db: Session = Depends(get_db),
):
    """Net worth summary for a given month (defaults to current)."""
    today = date.today()
    año = año or today.year
    mes = mes or today.month

    activos = db.query(PatrimonioAsset).filter(PatrimonioAsset.is_active == True).all()
    deudas = _get_patrimonio_debts(db)

    detalle_activos = []
    for a in activos:
        valor = calcular_valor_activo_en_mes(a, año, mes)
        d = a.to_dict()
        d["valor_actual"] = round(valor, 2)
        if float(a.valor_adquisicion) > 0:
            d["pct_cambio"] = round((valor / float(a.valor_adquisicion) - 1) * 100, 2)
        else:
            d["pct_cambio"] = 0
        detalle_activos.append(d)

    detalle_deudas = []
    for debt in deudas:
        saldo = saldo_deuda_en_mes(debt, año, mes, db=db)
        monto = float(debt.original_amount)
        n = _debt_term_months(debt)
        r = _debt_annual_rate(debt) / 12

        if r > 0 and n > 0:
            cuota = monto * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
        elif n > 0:
            cuota = monto / n
        else:
            cuota = 0

        # Project end date
        fi = debt.start_date
        if fi and n > 0:
            end_m = (fi.month - 1 + n) % 12 + 1
            end_y = fi.year + (fi.month - 1 + n) // 12
            fecha_fin = date(end_y, end_m, 1).isoformat()
        else:
            fecha_fin = None

        tipo_map = {"mortgage": "hipoteca", "credit_loan": "consumo"}
        detalle_deudas.append({
            "id": debt.id,
            "nombre": debt.name,
            "tipo": tipo_map.get(debt.debt_type, debt.debt_type),
            "monto_original": monto,
            "institution": debt.institution,
            "saldo_actual": round(saldo, 2),
            "cuota_mensual": round(cuota, 2),
            "progreso": round((1 - saldo / monto) * 100, 2) if monto > 0 else 100,
            "fecha_fin_proyectada": fecha_fin,
        })

    resumen = calcular_patrimonio_en_mes(activos, deudas, año, mes, db=db)

    return {
        "año": año,
        "mes": mes,
        "total_activos": round(resumen["total_activos"], 2),
        "total_deudas": round(resumen["total_deudas"], 2),
        "patrimonio_neto": round(resumen["patrimonio_neto"], 2),
        "activos": detalle_activos,
        "deudas": detalle_deudas,
    }


@router.get("/timeline")
def patrimonio_timeline(
    desde: str = Query(default=None, description="YYYY-MM"),
    hasta: str = Query(default=None, description="YYYY-MM"),
    db: Session = Depends(get_db),
):
    """Monthly net worth timeline."""
    today = date.today()
    if desde:
        parts = desde.split("-")
        desde_año, desde_mes = int(parts[0]), int(parts[1])
    else:
        desde_año = today.year - 2
        desde_mes = today.month

    if hasta:
        parts = hasta.split("-")
        hasta_año, hasta_mes = int(parts[0]), int(parts[1])
    else:
        hasta_año = today.year + 2
        hasta_mes = today.month

    activos = db.query(PatrimonioAsset).filter(PatrimonioAsset.is_active == True).all()
    deudas = _get_patrimonio_debts(db)

    tl = timeline_patrimonio(activos, deudas, desde_año, desde_mes, hasta_año, hasta_mes, db=db)
    for row in tl:
        row["total_activos"] = round(row["total_activos"], 2)
        row["total_deudas"] = round(row["total_deudas"], 2)
        row["patrimonio_neto"] = round(row["patrimonio_neto"], 2)
    return tl


# ── Assets CRUD ──────────────────────────────────────────────────────


@router.get("/activos")
def list_activos(db: Session = Depends(get_db)):
    return [a.to_dict() for a in db.query(PatrimonioAsset).order_by(PatrimonioAsset.id).all()]


@router.post("/activos")
def create_activo(payload: AssetCreate, db: Session = Depends(get_db)):
    asset = PatrimonioAsset(**payload.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset.to_dict()


@router.get("/activos/{asset_id}")
def get_activo(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(PatrimonioAsset).get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset.to_dict()


@router.put("/activos/{asset_id}")
def update_activo(asset_id: int, payload: AssetUpdate, db: Session = Depends(get_db)):
    asset = db.query(PatrimonioAsset).get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(asset, k, v)
    db.commit()
    db.refresh(asset)
    return asset.to_dict()


@router.delete("/activos/{asset_id}")
def delete_activo(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(PatrimonioAsset).get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    db.delete(asset)
    db.commit()
    return {"ok": True}


@router.get("/activos/{asset_id}/timeline")
def activo_timeline(
    asset_id: int,
    desde: str = Query(default=None),
    hasta: str = Query(default=None),
    db: Session = Depends(get_db),
):
    asset = db.query(PatrimonioAsset).get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    today = date.today()
    if desde:
        p = desde.split("-")
        d_y, d_m = int(p[0]), int(p[1])
    else:
        d_y, d_m = asset.fecha_adquisicion.year, 1

    if hasta:
        p = hasta.split("-")
        h_y, h_m = int(p[0]), int(p[1])
    else:
        h_y, h_m = today.year + 5, 12

    result = []
    y, m = d_y, d_m
    while (y, m) <= (h_y, h_m):
        val = calcular_valor_activo_en_mes(asset, y, m)
        result.append({"año": y, "mes": m, "valor": round(val, 2)})
        m += 1
        if m > 12:
            m = 1
            y += 1
    return result


