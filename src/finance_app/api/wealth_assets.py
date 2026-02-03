"""
Wealth assets API endpoints
"""
from datetime import date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models import WealthAsset, Currency, Debt
from finance_app.api.reports import get_exchange_rate, convert_to_currency
from finance_app.utils.wealth import apply_annual_appreciation_on_january, apply_depreciation

router = APIRouter()


class WealthAssetCreate(BaseModel):
    name: str
    asset_class: str
    investment_type: Optional[str] = None
    value: float = 0.0
    return_rate: Optional[float] = None
    return_amount: Optional[float] = None
    expected_appreciation_rate: Optional[float] = None
    depreciation_method: Optional[str] = None
    depreciation_rate: Optional[float] = None
    depreciation_years: Optional[int] = None
    depreciation_salvage_value: Optional[float] = None
    depreciation_start_date: Optional[date] = None
    currency_id: int
    mortgage_debt_id: Optional[int] = None
    as_of_date: Optional[date] = None
    notes: Optional[str] = None


class WealthAssetUpdate(BaseModel):
    name: Optional[str] = None
    asset_class: Optional[str] = None
    investment_type: Optional[str] = None
    value: Optional[float] = None
    return_rate: Optional[float] = None
    return_amount: Optional[float] = None
    expected_appreciation_rate: Optional[float] = None
    depreciation_method: Optional[str] = None
    depreciation_rate: Optional[float] = None
    depreciation_years: Optional[int] = None
    depreciation_salvage_value: Optional[float] = None
    depreciation_start_date: Optional[date] = None
    currency_id: Optional[int] = None
    mortgage_debt_id: Optional[int] = None
    as_of_date: Optional[date] = None
    notes: Optional[str] = None


INVESTMENT_TYPES = [
    "Acciones",
    "Bonos",
    "ETF",
    "Fondos mutuos",
    "Fondos indexados",
    "CDT",
    "Cripto",
    "Private equity",
    "Capital semilla",
    "Fiducia (p.ej. acciones de hotel)",
    "REIT",
    "Commodities (oro, petróleo)",
    "Crowdfunding",
    "Otros"
]


@router.get("/investment-types")
def get_investment_types():
    return {"investment_types": INVESTMENT_TYPES}


@router.get("/")
def list_wealth_assets(
    asset_class: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    query = db.query(WealthAsset)
    if asset_class:
        query = query.filter(WealthAsset.asset_class == asset_class)

    assets = query.order_by(WealthAsset.as_of_date.desc(), WealthAsset.id.desc()).all()

    exchange_rate = get_exchange_rate(db)
    total_value = 0.0
    results = []

    for asset in assets:
        if asset.asset_class == "inmueble":
            effective_value = apply_annual_appreciation_on_january(
                asset.value,
                asset.expected_appreciation_rate,
                asset.as_of_date,
                date.today()
            )
        elif asset.asset_class == "activo":
            effective_value = apply_depreciation(
                asset.value,
                asset.depreciation_method,
                asset.depreciation_rate,
                asset.depreciation_years,
                asset.depreciation_salvage_value,
                asset.depreciation_start_date or asset.as_of_date,
                date.today()
            )
        else:
            effective_value = asset.value
        converted_value = convert_to_currency(
            effective_value,
            asset.currency_id,
            currency_id,
            exchange_rate
        )
        total_value += converted_value
        asset_data = asset.to_dict()
        asset_data["value_converted"] = converted_value
        if asset.asset_class == "inmueble":
            asset_data["value_appreciated"] = effective_value
        if asset.asset_class == "activo":
            asset_data["value_depreciated"] = effective_value
        results.append(asset_data)

    currency = db.query(Currency).get(currency_id)

    return {
        "assets": results,
        "total_value": round(total_value, 2),
        "currency": currency.to_dict() if currency else None
    }


@router.post("/")
def create_wealth_asset(asset_data: WealthAssetCreate, db: Session = Depends(get_db)):
    currency = db.query(Currency).get(asset_data.currency_id)
    if not currency:
        raise HTTPException(status_code=400, detail="Currency not found")

    if asset_data.mortgage_debt_id:
        mortgage = db.query(Debt).get(asset_data.mortgage_debt_id)
        if not mortgage or mortgage.debt_type != "mortgage":
            raise HTTPException(status_code=400, detail="Mortgage debt not found")

    asset = WealthAsset(
        name=asset_data.name,
        asset_class=asset_data.asset_class,
        investment_type=asset_data.investment_type,
        value=asset_data.value,
        return_rate=asset_data.return_rate,
        return_amount=asset_data.return_amount,
        expected_appreciation_rate=asset_data.expected_appreciation_rate,
        depreciation_method=asset_data.depreciation_method,
        depreciation_rate=asset_data.depreciation_rate,
        depreciation_years=asset_data.depreciation_years,
        depreciation_salvage_value=asset_data.depreciation_salvage_value,
        depreciation_start_date=asset_data.depreciation_start_date,
        currency_id=asset_data.currency_id,
        mortgage_debt_id=asset_data.mortgage_debt_id,
        as_of_date=asset_data.as_of_date or date.today(),
        notes=asset_data.notes
    )

    db.add(asset)
    db.commit()
    db.refresh(asset)

    return asset.to_dict()


@router.put("/{asset_id}")
def update_wealth_asset(asset_id: int, asset_data: WealthAssetUpdate, db: Session = Depends(get_db)):
    asset = db.query(WealthAsset).get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if asset_data.currency_id is not None:
        currency = db.query(Currency).get(asset_data.currency_id)
        if not currency:
            raise HTTPException(status_code=400, detail="Currency not found")
        asset.currency_id = asset_data.currency_id

    if asset_data.mortgage_debt_id is not None:
        if asset_data.mortgage_debt_id == 0:
            asset.mortgage_debt_id = None
        else:
            mortgage = db.query(Debt).get(asset_data.mortgage_debt_id)
            if not mortgage or mortgage.debt_type != "mortgage":
                raise HTTPException(status_code=400, detail="Mortgage debt not found")
            asset.mortgage_debt_id = asset_data.mortgage_debt_id

    for field, value in asset_data.dict(exclude_unset=True).items():
        if field in {"currency_id", "mortgage_debt_id"}:
            continue
        setattr(asset, field, value)

    db.commit()
    db.refresh(asset)

    return asset.to_dict()


@router.delete("/{asset_id}")
def delete_wealth_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(WealthAsset).get(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    db.delete(asset)
    db.commit()

    return {"success": True}
