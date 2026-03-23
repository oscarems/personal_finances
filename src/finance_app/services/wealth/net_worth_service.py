"""
Servicio de Patrimonio Neto (Net Worth)

Módulo central para calcular el patrimonio neto (activos - pasivos) en cualquier
fecha o rango de fechas, con soporte para proyecciones futuras.

Componentes de activos:
  - Bienes inmuebles (con apreciación anual)
  - Activos depreciables (vehículos, equipos, etc.)
  - Inversiones (con movimientos transaccionales)
  - Saldos de cuentas bancarias (checking, savings, cash, CDT)

Componentes de pasivos:
  - Hipotecas (saldo principal vía tabla de amortización)
  - Créditos de libre inversión (saldo principal vía tabla de amortización)
  - Tarjetas de crédito (saldo actual)

Arquitectura:
  - Las funciones de cálculo son puras: reciben datos ya consultados.
  - Solo las funciones "orquestadoras" (build_*) reciben la sesión de BD.
  - Se reutilizan servicios existentes (amortización, tasas de cambio, etc.).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from finance_app.models import (
    Account,
    Currency,
    Debt,
    DebtAmortizationMonthly,
    ExchangeRate,
    Transaction,
    WealthAsset,
)
from finance_app.services.debt.amortization_service import (
    ensure_debt_amortization_records,
    fetch_amortization_for_month,
    fetch_amortization_range,
)
from finance_app.services.debt.balance_service import (
    calculate_mortgage_principal_balance,
)
from finance_app.services.wealth.helpers import (
    apply_annual_appreciation_on_january,
    apply_depreciation,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tipos de datos para resultados
# ---------------------------------------------------------------------------

@dataclass
class AssetSnapshot:
    """Valor de un activo individual en una fecha dada."""
    asset_id: int
    name: str
    asset_class: str
    category: str  # "bienes", "inversiones", o "cuentas"
    value_original: float  # Valor en moneda original
    value_converted: float  # Valor convertido a moneda objetivo
    currency_id: int


@dataclass
class LiabilitySnapshot:
    """Valor de un pasivo individual en una fecha dada."""
    debt_id: int
    name: str
    debt_type: str
    balance_original: float  # Saldo en moneda original
    balance_converted: float  # Saldo convertido a moneda objetivo
    currency_code: str


@dataclass
class NetWorthSnapshot:
    """Fotografía completa del patrimonio neto en una fecha dada."""
    reference_date: date
    total_assets: float
    total_liabilities: float
    net_worth: float
    # Desglose de activos por categoría
    assets_by_category: Dict[str, float] = field(default_factory=dict)
    # Detalle individual (opcional, para reportes detallados)
    asset_details: List[AssetSnapshot] = field(default_factory=list)
    liability_details: List[LiabilitySnapshot] = field(default_factory=list)


@dataclass
class NetWorthTimeline:
    """Serie temporal de patrimonio neto con metadatos."""
    start_date: date
    end_date: date
    snapshots: List[NetWorthSnapshot]
    change: float = 0.0
    change_percentage: float = 0.0
    current_net_worth: float = 0.0
    totals_by_category: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Funciones auxiliares puras (sin acceso a BD)
# ---------------------------------------------------------------------------

def _month_start(day: date) -> date:
    """Retorna el primer día del mes."""
    return day.replace(day=1)


def _month_end(day: date) -> date:
    """Retorna el último día del mes."""
    return day.replace(day=1) + relativedelta(months=1) - relativedelta(days=1)


def _iter_months(start_month: date, end_month: date) -> Iterable[date]:
    """Genera el primer día de cada mes en el rango [start, end]."""
    current = _month_start(start_month)
    while current <= _month_start(end_month):
        yield current
        current += relativedelta(months=1)


def _get_exchange_rate(db: Session) -> float:
    """Obtiene la tasa de cambio USD/COP más reciente."""
    rate = db.query(ExchangeRate).order_by(ExchangeRate.date.desc()).first()
    return rate.rate if rate else 4000.0


def _convert_to_currency(
    amount: float,
    from_currency_id: int,
    to_currency_id: int,
    exchange_rate: float,
) -> float:
    """Convierte un monto entre monedas usando la tasa USD/COP."""
    if from_currency_id == to_currency_id:
        return amount
    # USD (id=2) a COP (id=1)
    if from_currency_id == 2 and to_currency_id == 1:
        return amount * exchange_rate
    # COP (id=1) a USD (id=2)
    if from_currency_id == 1 and to_currency_id == 2:
        return amount / exchange_rate
    return amount


def _asset_category(asset: WealthAsset) -> Optional[str]:
    """Clasifica un activo en la categoría de patrimonio correspondiente."""
    if asset.asset_class in {"inmueble", "activo"}:
        return "bienes"
    if asset.asset_class == "inversion":
        return "inversiones"
    return None


def _compute_asset_base_value(asset: WealthAsset, reference_date: date) -> float:
    """
    Calcula el valor base de un activo según su clase (apreciación o depreciación).

    Para inmuebles: aplica apreciación anual compuesta.
    Para activos: aplica depreciación según el método configurado.
    Para inversiones: retorna el valor nominal.
    """
    if asset.asset_class == "inmueble":
        return apply_annual_appreciation_on_january(
            asset.value,
            asset.expected_appreciation_rate,
            asset.as_of_date,
            reference_date,
        )
    elif asset.asset_class == "activo":
        return apply_depreciation(
            asset.value,
            asset.depreciation_method,
            asset.depreciation_rate,
            asset.depreciation_years,
            asset.depreciation_salvage_value,
            asset.depreciation_start_date or asset.as_of_date,
            reference_date,
        )
    return asset.value or 0.0


def _compute_asset_value_at_date(
    asset: WealthAsset,
    target_date: date,
    transactions_by_asset: Dict[int, List[Transaction]],
    exchange_rate: float,
) -> Optional[float]:
    """
    Calcula el valor de un activo a una fecha específica,
    incluyendo movimientos transaccionales (compras/ventas de inversiones).

    Retorna None si el activo aún no existía en la fecha objetivo.
    """
    # Si el activo no existía aún, no lo incluimos
    if asset.as_of_date and asset.as_of_date > target_date:
        return None

    # Calcular valor base según tipo de activo
    base_value = _compute_asset_base_value(asset, target_date)

    # Aplicar ajustes transaccionales (compras/ventas de inversiones)
    anchor_date = asset.as_of_date or date.min
    transaction_adjustments = 0.0
    for tx in transactions_by_asset.get(asset.id, []):
        if not tx.date or tx.date <= anchor_date:
            continue
        if tx.date > target_date:
            continue
        # Movimiento negativo en cuenta = compra de inversión (suma al activo)
        movement = -tx.amount
        transaction_adjustments += _convert_to_currency(
            movement,
            tx.currency_id,
            asset.currency_id,
            exchange_rate,
        )

    return max(0.0, base_value + transaction_adjustments)


def _compute_account_balances_at_date(
    accounts: List[Account],
    target_date: date,
    all_transactions: List[Transaction],
    currency_id: int,
    exchange_rate: float,
) -> Tuple[float, List[AssetSnapshot]]:
    """
    Calcula los saldos de cuentas bancarias a una fecha específica,
    reconstruyendo el balance histórico a partir del saldo actual y transacciones.

    Solo incluye cuentas de tipo: checking, savings, cash, cdt.
    Excluye cuentas de deuda (credit_card, credit_loan, mortgage) ya que
    esas se capturan como pasivos.

    Retorna (total_convertido, lista_de_snapshots).
    """
    # Tipos de cuenta que representan activos líquidos
    ASSET_ACCOUNT_TYPES = {"checking", "savings", "cash", "cdt", "investment"}

    total = 0.0
    snapshots: List[AssetSnapshot] = []
    today = date.today()

    for account in accounts:
        if account.type not in ASSET_ACCOUNT_TYPES:
            continue

        # Reconstruir saldo histórico: saldo_actual - sum(transacciones después de target_date)
        current_balance = account.balance or 0.0
        future_movements = sum(
            tx.amount
            for tx in all_transactions
            if tx.account_id == account.id and tx.date and tx.date > target_date
        )
        historical_balance = current_balance - future_movements

        converted = _convert_to_currency(
            historical_balance,
            account.currency_id,
            currency_id,
            exchange_rate,
        )
        total += converted
        snapshots.append(AssetSnapshot(
            asset_id=account.id,
            name=account.name,
            asset_class=account.type,
            category="cuentas",
            value_original=historical_balance,
            value_converted=round(converted, 2),
            currency_id=account.currency_id,
        ))

    return round(total, 2), snapshots


# ---------------------------------------------------------------------------
# Funciones de cálculo de pasivos
# ---------------------------------------------------------------------------

def _compute_liabilities_at_date(
    db: Session,
    debts: List[Debt],
    target_month_start: date,
    target_month_end: date,
    amortization_records: Dict[Tuple[int, date], DebtAmortizationMonthly],
    currency_id: int,
    exchange_rate: float,
    currency_map: Dict[str, int],
) -> Tuple[float, Dict[str, float], List[LiabilitySnapshot]]:
    """
    Calcula el total de pasivos a una fecha determinada.

    Usa la tabla de amortización para préstamos e hipotecas,
    y el saldo actual para tarjetas de crédito.

    Retorna (total, desglose_por_tipo, detalle).
    """
    total = 0.0
    by_type: Dict[str, float] = {}
    details: List[LiabilitySnapshot] = []

    for debt in debts:
        debt_currency_id = currency_map.get(debt.currency_code, currency_id)
        balance = 0.0

        if debt.debt_type == "mortgage":
            # Para hipotecas usamos el motor de amortización directamente
            balance = calculate_mortgage_principal_balance(
                db, debt, as_of_date=target_month_end,
            )
        else:
            # Para otros tipos, buscar en tabla de amortización
            record = amortization_records.get((debt.id, target_month_start))
            if record:
                balance = float(record.principal_remaining)
            elif debt.debt_type == "credit_card":
                # Tarjetas de crédito: usar saldo actual (no tienen amortización)
                balance = debt.current_balance or 0.0

        converted = _convert_to_currency(balance, debt_currency_id, currency_id, exchange_rate)
        total += converted

        # Acumular por tipo de deuda
        by_type[debt.debt_type] = by_type.get(debt.debt_type, 0.0) + converted

        details.append(LiabilitySnapshot(
            debt_id=debt.id,
            name=debt.name,
            debt_type=debt.debt_type,
            balance_original=round(balance, 2),
            balance_converted=round(converted, 2),
            currency_code=debt.currency_code,
        ))

    return round(total, 2), by_type, details


# ---------------------------------------------------------------------------
# Funciones orquestadoras (con acceso a BD)
# ---------------------------------------------------------------------------

def compute_net_worth_at_date(
    db: Session,
    target_date: date,
    currency_id: int = 1,
    include_accounts: bool = True,
    include_details: bool = False,
) -> NetWorthSnapshot:
    """
    Calcula el patrimonio neto completo en una fecha específica.

    Args:
        db: Sesión de base de datos.
        target_date: Fecha para la cual calcular el patrimonio.
        currency_id: Moneda objetivo para la conversión (1=COP, 2=USD).
        include_accounts: Si True, incluye saldos de cuentas bancarias como activos.
        include_details: Si True, incluye desglose individual de activos y pasivos.

    Returns:
        NetWorthSnapshot con el patrimonio neto desglosado.
    """
    exchange_rate = _get_exchange_rate(db)
    month_start = _month_start(target_date)
    month_end = _month_end(target_date)

    # --- Cargar datos necesarios de BD (una sola vez) ---
    wealth_assets = db.query(WealthAsset).all()
    debts = db.query(Debt).all()
    currencies = db.query(Currency).all()
    currency_map = {c.code: c.id for c in currencies}

    # Cargar transacciones vinculadas a activos de inversión
    asset_ids = {a.id for a in wealth_assets}
    asset_transactions = (
        db.query(Transaction)
        .filter(Transaction.investment_asset_id.in_(asset_ids))
        .all()
        if asset_ids
        else []
    )
    transactions_by_asset: Dict[int, List[Transaction]] = {}
    for tx in asset_transactions:
        if tx.investment_asset_id is not None:
            transactions_by_asset.setdefault(tx.investment_asset_id, []).append(tx)

    # --- Calcular activos (wealth assets) ---
    totals_by_category: Dict[str, float] = {"bienes": 0.0, "inversiones": 0.0}
    asset_details: List[AssetSnapshot] = []

    for asset in wealth_assets:
        category = _asset_category(asset)
        if category is None:
            continue

        value = _compute_asset_value_at_date(
            asset, month_end, transactions_by_asset, exchange_rate,
        )
        if value is None:
            continue

        converted = _convert_to_currency(value, asset.currency_id, currency_id, exchange_rate)
        totals_by_category[category] += converted

        if include_details:
            asset_details.append(AssetSnapshot(
                asset_id=asset.id,
                name=asset.name,
                asset_class=asset.asset_class,
                category=category,
                value_original=round(value, 2),
                value_converted=round(converted, 2),
                currency_id=asset.currency_id,
            ))

    # --- Calcular saldos de cuentas bancarias (opcional) ---
    if include_accounts:
        accounts = db.query(Account).filter(Account.is_closed == False).all()
        all_account_transactions = db.query(Transaction).all()
        account_total, account_snapshots = _compute_account_balances_at_date(
            accounts, month_end, all_account_transactions, currency_id, exchange_rate,
        )
        totals_by_category["cuentas"] = account_total
        if include_details:
            asset_details.extend(account_snapshots)

    total_assets = sum(totals_by_category.values())

    # --- Calcular pasivos ---
    ensure_debt_amortization_records(db, month_start, month_start)
    amortization_records = fetch_amortization_range(
        db, month_start, month_start, [d.id for d in debts],
    )
    total_liabilities, _, liability_details_list = _compute_liabilities_at_date(
        db, debts, month_start, month_end,
        amortization_records, currency_id, exchange_rate, currency_map,
    )

    return NetWorthSnapshot(
        reference_date=target_date,
        total_assets=round(total_assets, 2),
        total_liabilities=total_liabilities,
        net_worth=round(total_assets - total_liabilities, 2),
        assets_by_category={k: round(v, 2) for k, v in totals_by_category.items()},
        asset_details=asset_details if include_details else [],
        liability_details=liability_details_list if include_details else [],
    )


def build_net_worth_timeline(
    db: Session,
    start_date: date,
    end_date: date,
    currency_id: int = 1,
    include_accounts: bool = False,
    include_projection_months: int = 0,
) -> NetWorthTimeline:
    """
    Construye la línea de tiempo mensual de patrimonio neto.

    Optimizado para consultas en lote: carga todos los datos necesarios
    una sola vez y luego itera mes a mes sin queries adicionales.

    Args:
        db: Sesión de base de datos.
        start_date: Fecha inicio del rango.
        end_date: Fecha fin del rango.
        currency_id: Moneda objetivo para conversión.
        include_accounts: Si True, incluye saldos de cuentas bancarias.
        include_projection_months: Meses de proyección más allá de end_date.

    Returns:
        NetWorthTimeline con la serie temporal completa.
    """
    exchange_rate = _get_exchange_rate(db)
    today = date.today()

    # Extender rango si hay proyección
    effective_end = end_date
    if include_projection_months > 0:
        effective_end = end_date + relativedelta(months=include_projection_months)

    # --- Carga única de datos ---
    wealth_assets = db.query(WealthAsset).all()
    debts = db.query(Debt).all()
    currencies = db.query(Currency).all()
    currency_map = {c.code: c.id for c in currencies}

    # Transacciones de inversión
    asset_ids = {a.id for a in wealth_assets}
    asset_transactions = (
        db.query(Transaction)
        .filter(Transaction.investment_asset_id.in_(asset_ids))
        .all()
        if asset_ids
        else []
    )
    transactions_by_asset: Dict[int, List[Transaction]] = {}
    for tx in asset_transactions:
        if tx.investment_asset_id is not None:
            transactions_by_asset.setdefault(tx.investment_asset_id, []).append(tx)

    # Cuentas y todas las transacciones (para reconstrucción histórica)
    accounts: List[Account] = []
    all_account_transactions: List[Transaction] = []
    if include_accounts:
        accounts = db.query(Account).filter(Account.is_closed == False).all()
        all_account_transactions = db.query(Transaction).all()

    # Amortización en lote para todo el rango
    ensure_debt_amortization_records(db, start_date, effective_end)
    amortization_records = fetch_amortization_range(
        db, start_date, effective_end, [d.id for d in debts],
    )

    # --- Iterar mes a mes ---
    snapshots: List[NetWorthSnapshot] = []

    for month_start in _iter_months(start_date, effective_end):
        month_end_date = _month_end(month_start)

        # Activos: wealth assets
        totals_by_cat: Dict[str, float] = {"bienes": 0.0, "inversiones": 0.0}
        for asset in wealth_assets:
            category = _asset_category(asset)
            if category is None:
                continue
            value = _compute_asset_value_at_date(
                asset, month_end_date, transactions_by_asset, exchange_rate,
            )
            if value is None:
                continue
            converted = _convert_to_currency(
                value, asset.currency_id, currency_id, exchange_rate,
            )
            totals_by_cat[category] += converted

        # Activos: cuentas bancarias (solo para datos históricos/actuales)
        if include_accounts and month_end_date <= today:
            acct_total, _ = _compute_account_balances_at_date(
                accounts, month_end_date, all_account_transactions,
                currency_id, exchange_rate,
            )
            totals_by_cat["cuentas"] = acct_total

        total_assets = sum(totals_by_cat.values())

        # Pasivos
        total_liabilities, _, _ = _compute_liabilities_at_date(
            db, debts, month_start, month_end_date,
            amortization_records, currency_id, exchange_rate, currency_map,
        )

        snapshots.append(NetWorthSnapshot(
            reference_date=month_start,
            total_assets=round(total_assets, 2),
            total_liabilities=total_liabilities,
            net_worth=round(total_assets - total_liabilities, 2),
            assets_by_category={k: round(v, 2) for k, v in totals_by_cat.items()},
        ))

    # --- Calcular cambio en el período ---
    change = 0.0
    change_pct = 0.0
    if len(snapshots) > 1:
        first_nw = snapshots[0].net_worth
        last_nw = snapshots[-1].net_worth
        change = last_nw - first_nw
        change_pct = (change / first_nw * 100) if first_nw != 0 else 0.0

    current_nw = snapshots[-1].net_worth if snapshots else 0.0
    final_cats = snapshots[-1].assets_by_category if snapshots else {}

    return NetWorthTimeline(
        start_date=start_date,
        end_date=end_date,
        snapshots=snapshots,
        change=round(change, 2),
        change_percentage=round(change_pct, 2),
        current_net_worth=round(current_nw, 2),
        totals_by_category={k: round(v, 2) for k, v in final_cats.items()},
    )


# ---------------------------------------------------------------------------
# Funciones de serialización (conversión a dict para API)
# ---------------------------------------------------------------------------

def snapshot_to_dict(snapshot: NetWorthSnapshot) -> dict:
    """Convierte un NetWorthSnapshot a diccionario para la API."""
    result = {
        "month": snapshot.reference_date.strftime("%Y-%m"),
        "month_name": snapshot.reference_date.strftime("%b %Y"),
        "assets": snapshot.total_assets,
        "assets_by_category": snapshot.assets_by_category,
        "liabilities": snapshot.total_liabilities,
        "net_worth": snapshot.net_worth,
    }
    if snapshot.asset_details:
        result["asset_details"] = [
            {
                "id": a.asset_id,
                "name": a.name,
                "class": a.asset_class,
                "category": a.category,
                "value": a.value_converted,
            }
            for a in snapshot.asset_details
        ]
    if snapshot.liability_details:
        result["liability_details"] = [
            {
                "id": l.debt_id,
                "name": l.name,
                "type": l.debt_type,
                "balance": l.balance_converted,
            }
            for l in snapshot.liability_details
        ]
    return result


def timeline_to_dict(timeline: NetWorthTimeline, currency: Optional[Currency] = None) -> dict:
    """Convierte un NetWorthTimeline a diccionario para la API."""
    return {
        "start_date": timeline.start_date.isoformat(),
        "end_date": timeline.end_date.isoformat(),
        "monthly": [snapshot_to_dict(s) for s in timeline.snapshots],
        "change": timeline.change,
        "change_percentage": timeline.change_percentage,
        "current_net_worth": timeline.current_net_worth,
        "totals_by_category": timeline.totals_by_category,
        "currency": currency.to_dict() if currency else None,
    }
