"""
Patrimonio calculator: asset valuation, debt balance from Debt model, net worth timeline.

Debts are read directly from the Debt model (single source of truth).
The AmortizationEngine is used for balance calculations on mortgage/credit_loan debts.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Asset depreciation (ported from services/wealth/helpers.py)
# ---------------------------------------------------------------------------

def aplicar_depreciacion(
    valor: float,
    method: str | None,
    rate: float | None,
    years: int | None,
    salvage_value: float | None,
    start_date: date | None,
    reference_date: date | None = None,
) -> float:
    """Apply depreciation to an asset value.

    Methods: linea_recta, saldo_decreciente, doble_saldo_decreciente.
    """
    if not method or method == "sin_depreciacion" or not start_date:
        return valor

    reference_date = reference_date or date.today()
    if reference_date <= start_date:
        return valor

    years_elapsed = (reference_date - start_date).days / 365
    if years_elapsed <= 0:
        return valor

    salvage_value = salvage_value or 0.0

    if method == "linea_recta":
        if not years or years <= 0:
            return valor
        depreciable = max(valor - salvage_value, 0)
        annual_dep = depreciable / years
        depreciated = valor - (annual_dep * years_elapsed)
    elif method == "saldo_decreciente":
        if not rate or rate <= 0:
            return valor
        depreciated = valor * ((1 - (rate / 100)) ** years_elapsed)
    elif method == "doble_saldo_decreciente":
        if not years or years <= 0:
            return valor
        r = 2 / years
        depreciated = valor * ((1 - r) ** years_elapsed)
    else:
        return valor

    return max(depreciated, salvage_value)


# ---------------------------------------------------------------------------
# Asset valuation
# ---------------------------------------------------------------------------

def calcular_valor_activo_en_mes(activo: Any, año: int, mes: int) -> float:
    """Calculate asset value for a given year/month.

    Valuation happens on January 1st each year. Value is constant Jan-Dec.
    Formula: valor_adquisicion * (1 + tasa_anual) ^ max(0, year - year_acquisition - 1)
    If queried year == acquisition year -> return valor_adquisicion.
    If queried date < acquisition date -> return 0.

    Then applies depreciation if configured.
    """
    fecha_adq = activo.fecha_adquisicion
    query_date = date(año, mes, 1)
    if query_date < date(fecha_adq.year, fecha_adq.month, 1):
        return 0.0

    valor = float(activo.valor_adquisicion)
    tasa = float(activo.tasa_anual)
    year_acq = fecha_adq.year

    if año == year_acq:
        appreciated = valor
    else:
        exponent = max(0, año - year_acq - 1)
        appreciated = valor * ((1 + tasa) ** exponent)

    # Apply depreciation if configured
    method = getattr(activo, "depreciation_method", None)
    if method and method != "sin_depreciacion":
        appreciated = aplicar_depreciacion(
            valor=appreciated,
            method=method,
            rate=getattr(activo, "depreciation_rate", None),
            years=getattr(activo, "depreciation_years", None),
            salvage_value=float(getattr(activo, "depreciation_salvage_value", None) or 0),
            start_date=getattr(activo, "depreciation_start_date", None),
            reference_date=query_date,
        )

    return appreciated


# ---------------------------------------------------------------------------
# Debt balance — uses AmortizationEngine directly on Debt objects
# ---------------------------------------------------------------------------

def saldo_deuda_en_mes(deuda: Any, año: int, mes: int, db: Optional[Session] = None) -> float:
    """Get debt outstanding balance at a specific year/month.

    Uses AmortizationEngine hybrid mode (real payments + projected future)
    when a db session is provided. Otherwise falls back to pure math.
    """
    if db:
        return _saldo_via_engine(deuda, año, mes, db)
    return _saldo_puro(deuda, año, mes)


def _saldo_puro(deuda: Any, año: int, mes: int) -> float:
    """Pure mathematical balance calculation (no payment history)."""
    monto = float(deuda.original_amount)
    # interest_rate is stored as percentage (e.g. 11.5 for 11.5%)
    rate = float(deuda.interest_rate or 0)
    tasa = rate / 100 if rate > 1 else rate
    plazo = int(deuda.term_months or 0) or (int(deuda.loan_years or 0) * 12)
    fecha_inicio = deuda.start_date

    if not plazo or not fecha_inicio:
        return monto

    query_date = date(año, mes, 1)
    start_date = date(fecha_inicio.year, fecha_inicio.month, 1)

    if query_date <= start_date:
        return monto

    months_elapsed = (año - fecha_inicio.year) * 12 + (mes - fecha_inicio.month)

    if months_elapsed >= plazo:
        return 0.0

    r = tasa / 12.0
    if r == 0:
        pago_capital_mensual = monto / plazo
        saldo = monto - pago_capital_mensual * months_elapsed
        return max(0.0, saldo)

    cuota = monto * (r * (1 + r) ** plazo) / ((1 + r) ** plazo - 1)
    saldo = monto
    for _ in range(months_elapsed):
        interes = saldo * r
        capital = cuota - interes
        saldo = saldo - capital
        if saldo <= 0:
            return 0.0

    return max(0.0, saldo)


def _saldo_via_engine(deuda: Any, año: int, mes: int, db: Session) -> float:
    """Balance via AmortizationEngine hybrid mode using real payment history."""
    from finance_app.services.debt.amortization_engine import AmortizationEngine

    engine = AmortizationEngine(db=db)
    return engine.balance_as_of(deuda, date(año, mes, 1), mode="hybrid")


# ---------------------------------------------------------------------------
# Net worth aggregation
# ---------------------------------------------------------------------------

def calcular_patrimonio_en_mes(
    activos: list[Any], deudas: list[Any], año: int, mes: int,
    db: Optional[Session] = None,
) -> dict:
    """Calculate total assets, total debts, and net worth for a month."""
    total_activos = sum(
        calcular_valor_activo_en_mes(a, año, mes) for a in activos
    )
    total_deudas = sum(
        saldo_deuda_en_mes(d, año, mes, db=db) for d in deudas
    )
    return {
        "año": año,
        "mes": mes,
        "total_activos": total_activos,
        "total_deudas": total_deudas,
        "patrimonio_neto": total_activos - total_deudas,
    }


def timeline_patrimonio(
    activos: list[Any],
    deudas: list[Any],
    desde_año: int,
    desde_mes: int,
    hasta_año: int,
    hasta_mes: int,
    db: Optional[Session] = None,
) -> list[dict]:
    """Generate monthly net-worth timeline from (desde_año, desde_mes) to (hasta_año, hasta_mes)."""
    result = []
    y, m = desde_año, desde_mes
    while (y, m) <= (hasta_año, hasta_mes):
        result.append(calcular_patrimonio_en_mes(activos, deudas, y, m, db=db))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return result
