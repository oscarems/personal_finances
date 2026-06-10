from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models.investment_asset import InvestmentAsset
from finance_app.models.investment_portfolio import InvestmentPortfolio
from finance_app.services import portfolio_service, price_history_service
from finance_app.services.portfolio_service import _enrich_asset

router = APIRouter()


class PortfolioCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    target_allocation: Optional[dict] = None
    moneda: str = "COP"


class AssetCreate(BaseModel):
    portfolio_id: Optional[int] = None
    simbolo: str
    nombre: str
    tipo: str
    asset_class: str
    unidades: float
    precio_compra: float
    fecha_compra: str
    moneda: str = "USD"
    notas: Optional[str] = None


class PriceCreate(BaseModel):
    fecha: str
    precio: float
    fuente: str = "manual"


@router.get("/")
def get_all_portfolios(db: Session = Depends(get_db)):
    try:
        return portfolio_service.get_all_portfolios(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
def create_portfolio(body: PortfolioCreate, db: Session = Depends(get_db)):
    try:
        return portfolio_service.create_portfolio(
            db,
            nombre=body.nombre,
            descripcion=body.descripcion,
            target_allocation=body.target_allocation,
            moneda=body.moneda,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/assets")
def get_all_assets(db: Session = Depends(get_db)):
    try:
        return price_history_service.get_all_assets_summary(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assets")
def create_asset(body: AssetCreate, db: Session = Depends(get_db)):
    try:
        return portfolio_service.create_asset(
            db,
            portfolio_id=body.portfolio_id,
            simbolo=body.simbolo,
            nombre=body.nombre,
            tipo=body.tipo,
            asset_class=body.asset_class,
            unidades=body.unidades,
            precio_compra=body.precio_compra,
            fecha_compra=body.fecha_compra,
            moneda=body.moneda,
            notas=body.notas,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/assets/{asset_id}")
def get_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(InvestmentAsset).filter_by(id=asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        return _enrich_asset(db, asset)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(InvestmentAsset).filter_by(id=asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        asset.activo = False
        db.commit()
        return {"success": True, "message": f"Asset '{asset.nombre}' deactivated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assets/{asset_id}/prices")
def add_price(asset_id: int, body: PriceCreate, db: Session = Depends(get_db)):
    asset = db.query(InvestmentAsset).filter_by(id=asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        return price_history_service.add_price(
            db,
            asset_id=asset_id,
            fecha=body.fecha,
            precio=body.precio,
            fuente=body.fuente,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/assets/{asset_id}/prices")
def get_price_history(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(InvestmentAsset).filter_by(id=asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        return price_history_service.get_price_history(db, asset_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{portfolio_id}")
def get_portfolio_detail(portfolio_id: int, db: Session = Depends(get_db)):
    result = portfolio_service.get_portfolio_detail(db, portfolio_id)
    if not result:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return result


@router.delete("/{portfolio_id}")
def delete_portfolio(portfolio_id: int, db: Session = Depends(get_db)):
    portfolio = db.query(InvestmentPortfolio).filter_by(id=portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    active_assets = db.query(InvestmentAsset).filter(
        InvestmentAsset.portfolio_id == portfolio_id,
        InvestmentAsset.activo == True,
    ).count()

    if active_assets > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Portfolio has {active_assets} active asset(s). Deactivate them first."
        )

    try:
        nombre = portfolio.nombre
        db.delete(portfolio)
        db.commit()
        return {"success": True, "message": f"Portfolio '{nombre}' deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{portfolio_id}/allocation")
def get_portfolio_allocation(portfolio_id: int, db: Session = Depends(get_db)):
    portfolio = db.query(InvestmentPortfolio).filter_by(id=portfolio_id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    try:
        return portfolio_service.get_portfolio_allocation(db, portfolio_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
