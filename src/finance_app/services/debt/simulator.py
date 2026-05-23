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
    currency_code: str


def _build_states(debts: list) -> List[_DebtState]:
    states = []
    for d in debts:
        balance = Decimal(str(d.current_balance or 0))
        if balance <= 0:
            continue
        rate_raw = d.annual_interest_rate if d.annual_interest_rate is not None else d.interest_rate
        monthly = _monthly_rate(float(rate_raw) if rate_raw is not None else None)
        min_pay = Decimal(str(d.monthly_payment or d.minimum_payment or 0))
        states.append(_DebtState(
            id=d.id,
            name=d.name,
            balance=balance,
            monthly_rate=monthly,
            min_payment=min_pay,
            currency_code=d.currency_code or "COP",
        ))
    return states


def _sort_states(states: List[_DebtState], strategy: str) -> List[_DebtState]:
    if strategy == "avalanche":
        return sorted(states, key=lambda s: s.monthly_rate, reverse=True)
    elif strategy == "snowball":
        return sorted(states, key=lambda s: s.balance)
    return states


def simulate_payoff(debts: list, extra_payment: float, strategy: str) -> dict:
    """
    Simulate debt payoff with an optional extra monthly payment.

    Returns payoff_date, payoff_date_extra, total_interest, total_interest_extra,
    interest_saved, months_saved, monthly_breakdown.
    """
    extra = Decimal(str(extra_payment)) if extra_payment else Decimal("0")
    if strategy not in ("avalanche", "snowball", "none"):
        strategy = "none"

    baseline_states = _build_states(debts)
    baseline_total_interest, baseline_months, baseline_breakdown = _run_simulation(
        baseline_states, Decimal("0"), strategy
    )

    extra_states = _build_states(debts)
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

    return {
        "payoff_date": payoff_date.isoformat(),
        "payoff_date_extra": payoff_date_extra.isoformat(),
        "total_interest": float(_round2(baseline_total_interest)),
        "total_interest_extra": float(_round2(extra_total_interest)),
        "interest_saved": float(_round2(baseline_total_interest - extra_total_interest)),
        "months_saved": baseline_months - extra_months,
        "monthly_breakdown": monthly_breakdown,
    }


def _run_simulation(
    states: List[_DebtState],
    extra: Decimal,
    strategy: str,
) -> tuple:
    balances = {s.id: s.balance for s in states}
    rates = {s.id: s.monthly_rate for s in states}
    min_payments = {s.id: s.min_payment for s in states}

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

            min_pay = min(min_payments[s.id], bal)
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
        total_balance = sum(b for b in balances.values() if b > 0)
        breakdown.append({
            "balance_total": _round2(total_balance),
            "interest_paid": _round2(month_interest),
        })
        month += 1

    return total_interest, month, breakdown
