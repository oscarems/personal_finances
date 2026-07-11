"""
Debt Payoff Simulator — Pure function, no DB access.

All monetary calculations use Decimal. Interest rates follow the effective annual
convention: monthly_rate = (1 + annual_rate)^(1/12) - 1
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from dateutil.relativedelta import relativedelta

TWOPLACES = Decimal("0.01")
MAX_MONTHS = 600


def _round2(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _monthly_rate(annual_rate_pct: Optional[float]) -> Decimal:
    if annual_rate_pct is None or annual_rate_pct == 0:
        return Decimal("0")
    annual = float(annual_rate_pct)
    if annual > 1:
        annual = annual / 100
    monthly = (1 + annual) ** (1 / 12) - 1
    return Decimal(str(monthly))


@dataclass
class _DebtState:
    id: int
    name: str
    balance: Decimal
    monthly_rate: Decimal
    min_payment: Decimal
    min_payment_pct: Decimal  # >0 means recalculate each month as % of balance
    currency_code: str


def _build_states(debts: list, balance_overrides: dict | None = None) -> List[_DebtState]:
    overrides = balance_overrides or {}
    states = []
    for d in debts:
        raw_balance = overrides.get(d.id) if d.id in overrides else (d.current_balance or 0)
        balance = Decimal(str(raw_balance))
        if balance <= 0:
            continue

        # Rate priority: monthly_interest_rate > annual_interest_rate > interest_rate
        mir = getattr(d, 'monthly_interest_rate', None)
        if mir is not None and float(mir) > 0:
            monthly = Decimal(str(float(mir) / 100))
        else:
            rate_raw = getattr(d, 'annual_interest_rate', None) or getattr(d, 'interest_rate', None)
            monthly = _monthly_rate(float(rate_raw) if rate_raw is not None else None)

        # Payment priority: monthly_payment > minimum_payment > min_payment_percentage of balance
        # monthly_payment and minimum_payment must be explicitly > 0 (0.0 is falsy but means "not set")
        mp = d.monthly_payment
        minp = d.minimum_payment
        pct = getattr(d, 'min_payment_percentage', None)

        min_payment_pct = Decimal("0")
        if mp is not None and float(mp) > 0:
            min_pay = Decimal(str(float(mp)))
        elif minp is not None and float(minp) > 0:
            min_pay = Decimal(str(float(minp)))
        elif pct is not None and float(pct) > 0:
            # Dynamic: recalculate each month. Store pct, initial value for reference.
            min_payment_pct = Decimal(str(float(pct) / 100))
            min_pay = _round2(balance * min_payment_pct)
        else:
            min_pay = Decimal("0")

        states.append(_DebtState(
            id=d.id,
            name=d.name,
            balance=balance,
            monthly_rate=monthly,
            min_payment=min_pay,
            min_payment_pct=min_payment_pct,
            currency_code=d.currency_code or "COP",
        ))
    return states


def _sort_states(states: List[_DebtState], strategy: str) -> List[_DebtState]:
    if strategy == "avalanche":
        return sorted(states, key=lambda s: s.monthly_rate, reverse=True)
    elif strategy == "snowball":
        return sorted(states, key=lambda s: s.balance)
    return states


def simulate_payoff(debts: list, extra_payment: float, strategy: str, balance_overrides: dict | None = None) -> dict:
    """
    Simulate debt payoff with an optional extra monthly payment.

    Returns payoff_date, payoff_date_extra, total_interest, total_interest_extra,
    interest_saved, months_saved, monthly_breakdown.
    """
    extra = Decimal(str(extra_payment)) if extra_payment else Decimal("0")
    if strategy not in ("avalanche", "snowball", "none"):
        strategy = "none"

    baseline_states = _build_states(debts, balance_overrides)
    baseline_total_interest, baseline_months, baseline_breakdown = _run_simulation(
        baseline_states, Decimal("0"), strategy
    )

    extra_states = _build_states(debts, balance_overrides)
    extra_total_interest, extra_months, extra_breakdown = _run_simulation(
        extra_states, extra, strategy
    )

    today = date.today()
    payoff_date = (today + relativedelta(months=baseline_months)).replace(day=1)
    payoff_date_extra = (today + relativedelta(months=extra_months)).replace(day=1)

    max_len = max(len(baseline_breakdown), len(extra_breakdown))
    monthly_breakdown = []
    for i in range(max_len):
        b = baseline_breakdown[i] if i < len(baseline_breakdown) else None
        e = extra_breakdown[i] if i < len(extra_breakdown) else None
        month_label = (today + relativedelta(months=i)).strftime("%Y-%m")
        monthly_breakdown.append({
            "month": month_label,
            "balance_total": float(b["balance_total"]) if b else 0.0,
            "balance_total_extra": float(e["balance_total"]) if e else 0.0,
            "interest_paid": float(b["interest_paid"]) if b else 0.0,
            "interest_paid_extra": float(e["interest_paid"]) if e else 0.0,
        })

    missing_rate = [s.name for s in baseline_states if s.monthly_rate == Decimal("0")]

    return {
        "payoff_date": payoff_date.isoformat(),
        "payoff_date_extra": payoff_date_extra.isoformat(),
        "total_interest": float(_round2(baseline_total_interest)),
        "total_interest_extra": float(_round2(extra_total_interest)),
        "interest_saved": float(_round2(baseline_total_interest - extra_total_interest)),
        "months_saved": baseline_months - extra_months,
        "monthly_breakdown": monthly_breakdown,
        "warnings": [f"'{n}' no tiene tasa de interés registrada — configúrala en Deudas para ver el ahorro en intereses." for n in missing_rate],
    }


def compare_strategies(debts: list, extra_payment: float = 0.0, balance_overrides: dict | None = None) -> dict:
    """Compara avalancha, bola de nieve y pago mínimo para el mismo conjunto de deudas.

    Returns:
        {
            "avalanche": {
                "months": int,
                "total_interest": float,
                "payoff_date": str,
                "interest_saved_vs_minimum": float,
                "months_saved_vs_minimum": int,
                "debt_payoff_order": [{"id": int, "name": str}]
            },
            "snowball": { ... mismos campos ... },
            "minimum_only": {
                "months": int,
                "total_interest": float,
                "payoff_date": str,
                "interest_saved_vs_minimum": 0.0,
                "months_saved_vs_minimum": 0
            }
        }
    """
    extra = float(extra_payment) if extra_payment else 0.0

    minimum_result = simulate_payoff(debts, extra_payment=0, strategy="none", balance_overrides=balance_overrides)
    minimum_months = minimum_result["months_saved"]  # baseline_months when extra=0 means months_saved=0
    # When extra=0, payoff_date == payoff_date_extra and months_saved == 0
    # We need the actual months count — derive from payoff_date
    today = date.today()

    def _months_to(iso_date: str) -> int:
        target = date.fromisoformat(iso_date)
        delta = (target.year - today.year) * 12 + (target.month - today.month)
        return max(delta, 0)

    min_months = _months_to(minimum_result["payoff_date"])
    min_interest = minimum_result["total_interest"]
    min_payoff_date = minimum_result["payoff_date"]

    def _build_scenario(strategy: str) -> dict:
        base = simulate_payoff(debts, extra_payment=0, strategy=strategy, balance_overrides=balance_overrides)
        base_months = _months_to(base["payoff_date"])
        base_interest = base["total_interest"]
        base_payoff_date = base["payoff_date"]

        if extra > 0:
            with_extra = simulate_payoff(debts, extra_payment=extra, strategy=strategy, balance_overrides=balance_overrides)
            scenario_months = _months_to(with_extra["payoff_date_extra"])
            scenario_interest = with_extra["total_interest_extra"]
            scenario_payoff_date = with_extra["payoff_date_extra"]
        else:
            scenario_months = base_months
            scenario_interest = base_interest
            scenario_payoff_date = base_payoff_date

        states = _build_states(debts)
        ordered = _sort_states(states, strategy)
        debt_payoff_order = [{"id": s.id, "name": s.name} for s in ordered]

        return {
            "months": scenario_months,
            "total_interest": scenario_interest,
            "payoff_date": scenario_payoff_date,
            "interest_saved_vs_minimum": round(min_interest - scenario_interest, 2),
            "months_saved_vs_minimum": min_months - scenario_months,
            "debt_payoff_order": debt_payoff_order,
        }

    return {
        "avalanche": _build_scenario("avalanche"),
        "snowball": _build_scenario("snowball"),
        "minimum_only": {
            "months": min_months,
            "total_interest": min_interest,
            "payoff_date": min_payoff_date,
            "interest_saved_vs_minimum": 0.0,
            "months_saved_vs_minimum": 0,
        },
    }


def _run_simulation(
    states: List[_DebtState],
    extra: Decimal,
    strategy: str,
) -> tuple:
    balances = {s.id: s.balance for s in states}
    rates = {s.id: s.monthly_rate for s in states}
    min_payments = {s.id: s.min_payment for s in states}
    min_payment_pcts = {s.id: s.min_payment_pct for s in states}

    total_interest = Decimal("0")
    breakdown = []
    month = 0

    while any(b > 0 for b in balances.values()) and month < MAX_MONTHS:
        month_interest = Decimal("0")

        for s in states:
            bal = balances[s.id]
            if bal <= 0:
                continue
            interest = _round2(bal * rates[s.id])
            bal = bal + interest
            month_interest += interest

            pct = min_payment_pcts[s.id]
            if pct > 0:
                # Dynamic: % of current balance (after interest), ensures we cover at least interest
                min_pay = _round2(bal * pct)
                if min_pay <= interest:
                    min_pay = interest + Decimal("1")
            else:
                min_pay = min_payments[s.id]

            min_pay = min(min_pay, bal)
            if min_pay <= 0:
                min_pay = interest + Decimal("1")
            bal = max(Decimal("0"), bal - min_pay)
            balances[s.id] = bal

        remaining_extra = extra
        priority_order = _sort_states(
            [s for s in states if balances[s.id] > 0], strategy
        )
        for s in priority_order:
            if remaining_extra <= 0:
                break
            applied = min(remaining_extra, balances[s.id])
            balances[s.id] -= applied
            remaining_extra -= applied

        total_interest += month_interest
        total_balance = sum((b for b in balances.values() if b > 0), Decimal("0"))
        breakdown.append({
            "balance_total": _round2(total_balance),
            "interest_paid": _round2(month_interest),
        })
        month += 1

    return total_interest, month, breakdown
