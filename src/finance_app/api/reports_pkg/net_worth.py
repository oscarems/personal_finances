"""
Net worth timeline endpoint.

Upserts the current month's snapshot on each call, then returns all stored
snapshots so the client can render a historical chart.
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models import Account, Debt
from finance_app.models.net_worth_snapshot import NetWorthSnapshot
from finance_app.models.patrimonio_asset import PatrimonioAsset
from finance_app.models.investment_asset import InvestmentAsset
from finance_app.models.asset_price_history import AssetPriceHistory
from finance_app.services.exchange_rate_service import get_current_exchange_rate
from finance_app.services.debt.balance_service import calculate_scheduled_principal_balance

router = APIRouter()

DEBT_ACCOUNT_TYPES = {"credit_card", "credit_loan", "mortgage"}


def _compute_current_net_worth(db: Session) -> dict:
    usd_rate = get_current_exchange_rate(db)

    def to_cop(amount: float, currency_code: str) -> float:
        if currency_code == "USD":
            return amount * usd_rate
        return amount

    # ── Liquid accounts (savings, checking, cash, etc.)
    accounts = db.query(Account).filter(
        Account.type.notin_(DEBT_ACCOUNT_TYPES)
    ).all()
    liquid_cop = sum(
        to_cop(a.balance or 0.0, a.currency.code if a.currency else "COP")
        for a in accounts
    )

    # ── Patrimonio assets (real estate, vehicles, etc.)
    activos = db.query(PatrimonioAsset).filter(PatrimonioAsset.is_active == True).all()
    patrimonio_cop = 0.0
    today = date.today()
    for a in activos:
        # Use simple appreciation formula same as patrimonio service
        years = (today - a.fecha_adquisicion).days / 365.25 if a.fecha_adquisicion else 0
        valor = float(a.valor_adquisicion) * ((1 + (a.tasa_anual or 0) / 100) ** years)
        patrimonio_cop += to_cop(valor, a.currency.code if a.currency else "COP")

    # ── Investment portfolio (use latest known price per asset)
    inv_assets = db.query(InvestmentAsset).filter(InvestmentAsset.activo == True).all()
    investment_cop = 0.0
    for asset in inv_assets:
        latest = (
            db.query(AssetPriceHistory)
            .filter(AssetPriceHistory.asset_id == asset.id)
            .order_by(AssetPriceHistory.fecha.desc())
            .first()
        )
        precio = latest.precio if latest else asset.precio_compra
        valor = (asset.unidades or 0) * (precio or 0)
        investment_cop += to_cop(valor, asset.moneda or "USD")

    total_assets = liquid_cop + patrimonio_cop + investment_cop

    # ── Liabilities (all active debts)
    debts = db.query(Debt).filter(Debt.is_active == True).all()

    def _debt_balance(d: Debt) -> float:
        if d.debt_type == "mortgage":
            return calculate_scheduled_principal_balance(d, today)
        return d.current_balance or 0.0

    liabilities_cop = sum(
        to_cop(_debt_balance(d), d.currency_code or "COP")
        for d in debts
    )

    return {
        "assets_cop": round(total_assets, 0),
        "liabilities_cop": round(liabilities_cop, 0),
        "net_cop": round(total_assets - liabilities_cop, 0),
    }


@router.get("/net-worth-timeline")
def get_net_worth_timeline(db: Session = Depends(get_db)):
    """Upsert current month snapshot and return full history."""
    current_month = date.today().strftime("%Y-%m")
    values = _compute_current_net_worth(db)

    snapshot = db.query(NetWorthSnapshot).filter(
        NetWorthSnapshot.month == current_month
    ).first()

    if snapshot:
        snapshot.assets_cop = values["assets_cop"]
        snapshot.liabilities_cop = values["liabilities_cop"]
        snapshot.net_cop = values["net_cop"]
        snapshot.updated_at = datetime.utcnow()
    else:
        snapshot = NetWorthSnapshot(
            month=current_month,
            **values,
        )
        db.add(snapshot)

    db.commit()

    all_snapshots = (
        db.query(NetWorthSnapshot)
        .order_by(NetWorthSnapshot.month)
        .all()
    )
    return [s.to_dict() for s in all_snapshots]
