"""Combined what-if simulator: one extra monthly payment dial → debt + emergency + FIRE."""
from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from finance_app.models import Debt
from finance_app.services.debt.simulator import simulate_payoff, compare_strategies
from finance_app.services.emergency_fund_service import calculate_emergency_coverage
from finance_app.services.fire_service import get_fire_dashboard


def _months_until(iso_date: str | None) -> int | None:
    if not iso_date:
        return None
    try:
        d = date.fromisoformat(iso_date[:10])
    except ValueError:
        return None
    today = date.today().replace(day=1)
    target = d.replace(day=1)
    return max(0, (target.year - today.year) * 12 + (target.month - today.month))


def simulate_what_if(db: Session, extra_monthly: float, strategy: str = "avalanche") -> dict:
    """Project impact of allocating `extra_monthly` toward debts / savings / investments.

    Assumptions (documented for UI):
    - Debt: entire extra goes to payoff (avalanche/snowball).
    - Emergency: extra treated as additional savings over 12 months.
    - FIRE: extra treated as annual investable savings (extra * 12).
    """
    extra = max(0.0, float(extra_monthly or 0))
    debts = db.query(Debt).filter(Debt.is_active == True).all()

    debt_block = None
    if debts:
        result = simulate_payoff(debts, extra, strategy)
        months_base = _months_until(result.get("payoff_date"))
        months_extra = _months_until(result.get("payoff_date_extra"))
        debt_block = {
            "baseline": {
                "months": months_base,
                "total_interest": result.get("total_interest"),
                "payoff_date": result.get("payoff_date"),
            },
            "with_extra": {
                "months": months_extra,
                "total_interest": result.get("total_interest_extra"),
                "payoff_date": result.get("payoff_date_extra"),
            },
            "months_saved": result.get("months_saved"),
            "interest_saved": result.get("interest_saved"),
            "warnings": result.get("warnings") or [],
            "comparison": compare_strategies(debts, extra) if extra > 0 else None,
        }

    coverage = calculate_emergency_coverage(db)
    funds = float(coverage.get("emergency_funds_total") or 0)
    expenses = float(coverage.get("essential_expenses_total") or 0)
    months_now = float(coverage.get("months_coverage") or 0)
    funds_with_extra = funds + extra * 12
    months_with_extra = (funds_with_extra / expenses) if expenses > 0 else months_now

    fire = get_fire_dashboard(db)
    patrimonio = float(fire.get("patrimonio_invertible") or 0)
    gastos = float(fire.get("gastos_anuales_esenciales") or 0)
    fire_number = gastos * 25
    ratio_now = float(fire.get("ratio_fire") or 0)
    anos_now = fire.get("anos_restantes")

    anos_with_extra = None
    if fire_number > 0 and patrimonio < fire_number:
        annual_extra = extra * 12
        faltante = fire_number - patrimonio
        if annual_extra > 0:
            anos_with_extra = round(faltante / annual_extra, 1)
        elif anos_now is not None:
            anos_with_extra = anos_now

    ratio_with_extra = (
        min(1.0, (patrimonio + extra * 12) / fire_number) if fire_number > 0 else ratio_now
    )

    return {
        "extra_monthly": extra,
        "strategy": strategy,
        "debt": debt_block,
        "emergency": {
            "months_now": round(months_now, 2),
            "months_with_extra_12m": round(months_with_extra, 2),
            "funds_now": round(funds, 2),
            "funds_with_extra_12m": round(funds_with_extra, 2),
            "essential_expenses": round(expenses, 2),
        },
        "fire": {
            "ratio_now": round(ratio_now, 4),
            "ratio_after_1y_extra": round(ratio_with_extra, 4),
            "anos_restantes_now": anos_now,
            "anos_restantes_with_extra": anos_with_extra,
            "patrimonio_invertible": round(patrimonio, 2),
            "fire_number": round(fire_number, 2),
        },
        "as_of": date.today().isoformat(),
        "note": (
            "Escenario hipotético: el pago extra se modela por separado en deudas, "
            "fondo de emergencia (12 meses) y FIRE (aporte anual = extra×12). "
            "No modifica datos reales."
        ),
    }
