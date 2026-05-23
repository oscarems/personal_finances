"""
Financial health endpoint.

Evaluates the monthly BUDGET against a configurable 50/30/20 allocation rule
and produces an adherence score measuring how closely actual spending tracks
what was budgeted.

Categorization:
- savings : rollover_type == 'accumulate'
- needs   : is_essential
- wants   : everything else (non-income)

Savings adherence rule
----------------------
Savings categories accumulate balance across months (rollover_type='accumulate').
A user can spend more than what was *assigned* this month as long as the cumulative
`available` balance stays >= 0.  Therefore:
  - Adherence for savings  → scored against `available` (cumulative balance)
  - Over-budget for savings → available < 0
  - Display metric         → available (not assigned - spent)

Expense adherence rule (needs / wants)
---------------------------------------
  - Adherence → scored against `assigned` (monthly budget)
  - Over-budget → spent > assigned
"""
from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.services.budget_service import get_month_budget
from .common import get_exchange_rate
from .income import get_income_total

router = APIRouter()


# ── Classification ────────────────────────────────────────────────────────────

def _classify(cat: dict) -> str:
    if cat.get("rollover_type") == "accumulate":
        return "savings"
    if cat.get("is_essential"):
        return "needs"
    return "wants"


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _rule_bucket_score(actual_pct: float, target_pct: float, bucket: str) -> float:
    """Score a single 50/30/20 bucket (0–100).
    needs/wants: overshooting is bad.
    savings: undershooting is bad, overshooting is capped at 100.
    """
    if target_pct <= 0:
        return 100.0
    if bucket == "savings":
        return min(100.0, actual_pct / target_pct * 100.0)
    if actual_pct <= target_pct:
        return 100.0
    over_ratio = (actual_pct - target_pct) / target_pct
    return max(0.0, 100.0 - over_ratio * 100.0)


def _adherence_score_expense(assigned: float, spent: float) -> float:
    """Expense adherence: penalise spending over the monthly assignment."""
    if assigned <= 0:
        return 100.0 if spent <= 0 else 0.0
    if spent <= assigned:
        return 100.0
    over_ratio = (spent - assigned) / assigned
    return max(0.0, 100.0 - over_ratio * 100.0)


def _adherence_score_savings(available: float, spent: float) -> float:
    """Savings adherence: penalise only when cumulative available < 0.
    Spending more than *assigned* this month is fine as long as the
    accumulated balance covers it.
    """
    if available >= 0:
        return 100.0
    # available is negative → overspent the accumulated balance
    # reference = what was spent (best proxy for the total that was available)
    ref = spent if spent > 0 else 1.0
    over_ratio = (-available) / ref
    return max(0.0, 100.0 - over_ratio * 100.0)


# ── Main endpoint ─────────────────────────────────────────────────────────────

@router.get("/financial-health")
def get_financial_health(
    month: Optional[str] = None,
    currency_code: str = "COP",
    needs_target: float = Query(50.0, ge=0, le=100),
    wants_target: float = Query(30.0, ge=0, le=100),
    savings_target: float = Query(20.0, ge=0, le=100),
    db: Session = Depends(get_db),
):
    # ── Date ──────────────────────────────────────────────────────────────────
    if month:
        year, mo = month.split("-")
        month_date = date(int(year), int(mo), 1)
    else:
        month_date = date.today().replace(day=1)

    budget = get_month_budget(db, month_date, currency_code=currency_code)
    if budget is None:
        return {"error": f"Unknown currency: {currency_code}"}

    # ── Income ────────────────────────────────────────────────────────────────
    currency_obj = budget.get("currency", {})
    currency_id  = currency_obj.get("id", 1)
    exchange_rate = get_exchange_rate(db)
    month_end = month_date + relativedelta(months=1)
    total_income = get_income_total(db, month_date, month_end, currency_id, exchange_rate)

    # ── Iterate categories ────────────────────────────────────────────────────
    buckets: dict[str, dict] = {
        "needs":   {"assigned": 0.0, "spent": 0.0, "available": 0.0, "categories": []},
        "wants":   {"assigned": 0.0, "spent": 0.0, "available": 0.0, "categories": []},
        "savings": {"assigned": 0.0, "spent": 0.0, "available": 0.0, "categories": []},
    }

    total_assigned = 0.0
    total_spent    = 0.0
    weighted_adherence_num = 0.0
    weighted_adherence_den = 0.0
    over_budget_categories: list[dict] = []

    for group in budget["groups"]:
        if group.get("is_income"):
            continue
        for cat in group["categories"]:
            assigned  = float(cat.get("assigned")  or 0.0)
            activity  = float(cat.get("activity")  or 0.0)
            available = float(cat.get("available") or 0.0)
            spent     = max(0.0, -activity)

            if assigned <= 0 and spent <= 0:
                continue

            bucket_name = _classify(cat)
            b = buckets[bucket_name]
            b["assigned"]  += assigned
            b["spent"]     += spent
            b["available"] += available

            b["categories"].append({
                "category_id":   cat.get("category_id"),
                "category_name": cat.get("category_name"),
                "group_name":    group.get("name"),
                "assigned":      assigned,
                "spent":         spent,
                "available":     available,
                "rollover_type": cat.get("rollover_type"),
                "is_essential":  cat.get("is_essential"),
            })

            total_assigned += assigned
            total_spent    += spent

            # ── Adherence score per category ──────────────────────────────
            is_savings = bucket_name == "savings"
            if is_savings:
                cat_score = _adherence_score_savings(available, spent)
                weight = spent if spent > 0 else assigned
            else:
                cat_score = _adherence_score_expense(assigned, spent)
                weight = assigned if assigned > 0 else spent

            weighted_adherence_num += cat_score * weight
            weighted_adherence_den += weight

            # ── Over-budget detection ─────────────────────────────────────
            if is_savings:
                if available < 0:
                    # base = what they had available before spending this month
                    # available = prior_rollover + assigned - spent
                    # => prior_rollover = available - assigned + spent
                    prior_rollover = available - assigned + spent
                    base = prior_rollover + assigned  # = spent + available
                    ref  = base if base > 0 else spent if spent > 0 else 1.0
                    over_budget_categories.append({
                        "category_name": cat.get("category_name"),
                        "group_name":    group.get("name"),
                        "assigned":      assigned,
                        "spent":         spent,
                        "available":     available,
                        "overspend":     -available,
                        "overspend_pct": (-available / ref * 100.0),
                        "is_savings":    True,
                    })
            else:
                if assigned > 0 and spent > assigned:
                    over_budget_categories.append({
                        "category_name": cat.get("category_name"),
                        "group_name":    group.get("name"),
                        "assigned":      assigned,
                        "spent":         spent,
                        "available":     available,
                        "overspend":     spent - assigned,
                        "overspend_pct": (spent - assigned) / assigned * 100.0,
                        "is_savings":    False,
                    })

    # ── Percentages of total assigned ─────────────────────────────────────────
    def _pct(v: float) -> float:
        return round(v / total_assigned * 100.0, 2) if total_assigned > 0 else 0.0

    for b in buckets.values():
        b["pct_of_assigned"] = _pct(b["assigned"])
        b["categories"].sort(key=lambda c: c["assigned"], reverse=True)

    # ── Normalize targets ─────────────────────────────────────────────────────
    target_sum = needs_target + wants_target + savings_target
    if target_sum <= 0:
        needs_t, wants_t, savings_t = 50.0, 30.0, 20.0
    else:
        needs_t   = needs_target   / target_sum * 100.0
        wants_t   = wants_target   / target_sum * 100.0
        savings_t = savings_target / target_sum * 100.0

    # ── 50/30/20 rule score ───────────────────────────────────────────────────
    rule_scores = {
        "needs":   _rule_bucket_score(buckets["needs"]["pct_of_assigned"],   needs_t,   "needs"),
        "wants":   _rule_bucket_score(buckets["wants"]["pct_of_assigned"],   wants_t,   "wants"),
        "savings": _rule_bucket_score(buckets["savings"]["pct_of_assigned"], savings_t, "savings"),
    }
    rule_score = round(sum(rule_scores.values()) / 3.0, 1)

    # ── Adherence score ───────────────────────────────────────────────────────
    adherence_score = round(
        weighted_adherence_num / weighted_adherence_den, 1
    ) if weighted_adherence_den > 0 else 100.0

    # ── Income-based analysis ─────────────────────────────────────────────────
    income_buckets: dict[str, float] = {}
    income_rule_scores: dict[str, float] = {}
    if total_income > 0:
        target_map = {"needs": needs_t, "wants": wants_t, "savings": savings_t}
        for name in ("needs", "wants", "savings"):
            # savings → assigned (lo que comprometiste ahorrar este mes)
            # needs/wants → spent (gasto real)
            if name == "savings":
                value = buckets["savings"]["assigned"]
            else:
                value = buckets[name]["spent"]
            income_buckets[name] = round(value / total_income * 100.0, 2)
            income_rule_scores[name] = _rule_bucket_score(
                income_buckets[name], target_map[name], name,
            )
        income_score = round(sum(income_rule_scores.values()) / 3.0, 1)
        # dinero libre = ingreso no gastado ni comprometido en ahorro
        total_used = buckets["needs"]["spent"] + buckets["wants"]["spent"] + buckets["savings"]["assigned"]
        income_unspent_pct = round((total_income - total_used) / total_income * 100.0, 2)
    else:
        for name in ("needs", "wants", "savings"):
            income_buckets[name] = 0.0
            income_rule_scores[name] = 0.0
        income_score = 0.0
        income_unspent_pct = 0.0

    # ── Overall score ─────────────────────────────────────────────────────────
    overall_score = round(0.6 * adherence_score + 0.4 * rule_score, 1)

    def _grade(s: float) -> str:
        if s >= 90: return "A"
        if s >= 80: return "B"
        if s >= 70: return "C"
        if s >= 60: return "D"
        return "F"

    # ── Insights (good / bad signals for the notifications panel) ────────────
    insights: list[dict] = []

    def _ins(kind: str, msg: str, detail: str = ""):
        insights.append({"kind": kind, "message": msg, "detail": detail})

    # Overall score insight
    if overall_score >= 90:
        _ins("good", "Salud financiera excelente este mes", f"Puntaje general: {overall_score}/100")
    elif overall_score >= 75:
        _ins("good", "Salud financiera buena", f"Puntaje general: {overall_score}/100")
    elif overall_score >= 60:
        _ins("warn", "Salud financiera aceptable — hay margen de mejora", f"Puntaje general: {overall_score}/100")
    else:
        _ins("bad", "Salud financiera bajo el mínimo recomendado", f"Puntaje general: {overall_score}/100")

    # Adherence
    if adherence_score >= 90:
        _ins("good", "Respetaste muy bien tu presupuesto por categoría", f"Cumplimiento: {adherence_score}/100")
    elif adherence_score < 70:
        n_over = sum(1 for c in over_budget_categories if not c["is_savings"])
        _ins("bad", f"{n_over} categoría{'s' if n_over != 1 else ''} de gasto se excedieron del presupuesto",
             f"Cumplimiento: {adherence_score}/100")

    # Savings adherence
    n_savings_over = sum(1 for c in over_budget_categories if c["is_savings"])
    if n_savings_over == 0 and buckets["savings"]["spent"] > 0:
        _ins("good", "Ninguna categoría de ahorro consumió más de lo acumulado",
             "El saldo disponible de todos tus ahorros es positivo")
    elif n_savings_over > 0:
        _ins("bad",
             f"{n_savings_over} categoría{'s' if n_savings_over != 1 else ''} de ahorro gastaron más de lo disponible",
             "El saldo acumulado quedó negativo — revisa si hubo un retiro no planeado")

    # Savings allocation
    sav_pct = buckets["savings"]["pct_of_assigned"]
    if sav_pct >= savings_t:
        _ins("good", f"Estás ahorrando el {sav_pct:.1f}% de tu presupuesto",
             f"Objetivo configurado: {savings_t:.1f}%")
    else:
        gap = savings_t - sav_pct
        _ins("warn", f"Estás ahorrando el {sav_pct:.1f}% — {gap:.1f}% por debajo de tu objetivo",
             f"Objetivo configurado: {savings_t:.1f}%")

    # Needs allocation
    needs_pct = buckets["needs"]["pct_of_assigned"]
    if needs_pct <= needs_t:
        _ins("good", f"Gastos esenciales dentro del objetivo ({needs_pct:.1f}% vs {needs_t:.1f}%)",
             "Tu distribución de necesidades es saludable")
    else:
        _ins("warn", f"Gastos esenciales por encima del objetivo ({needs_pct:.1f}% vs {needs_t:.1f}%)",
             "Considera si hay gastos fijos que puedas reducir")

    # Wants allocation
    wants_pct = buckets["wants"]["pct_of_assigned"]
    if wants_pct <= wants_t:
        _ins("good", f"Gastos discrecionales dentro del objetivo ({wants_pct:.1f}% vs {wants_t:.1f}%)")
    else:
        _ins("warn", f"Gastos discrecionales por encima del objetivo ({wants_pct:.1f}% vs {wants_t:.1f}%)",
             "Revisa si hay gastos de deseos que puedas recortar")

    # Income ratio
    if total_income > 0:
        spent_of_income = total_spent / total_income * 100.0
        if income_unspent_pct >= 10:
            _ins("good", f"Queda el {income_unspent_pct:.1f}% del ingreso sin usar",
                 "Buen margen de seguridad frente a imprevistos")
        elif income_unspent_pct < 0:
            _ins("bad", "Gastaste más de lo que ingresaste este mes",
                 f"Déficit: {abs(income_unspent_pct):.1f}% del ingreso mensual")

    return {
        "month":    month_date.strftime("%Y-%m"),
        "currency": budget.get("currency"),
        "targets": {
            "needs":   round(needs_t,   2),
            "wants":   round(wants_t,   2),
            "savings": round(savings_t, 2),
        },
        "totals": {
            "assigned":  total_assigned,
            "spent":     total_spent,
            "remaining": total_assigned - total_spent,
        },
        "buckets": {
            name: {
                "assigned":        b["assigned"],
                "spent":           b["spent"],
                "available":       b["available"],
                "pct_of_assigned": b["pct_of_assigned"],
                "target_pct":      round(
                    {"needs": needs_t, "wants": wants_t, "savings": savings_t}[name], 2
                ),
                "rule_score":  round(rule_scores[name], 1),
                "categories":  b["categories"],
            }
            for name, b in buckets.items()
        },
        "scores": {
            "overall":   overall_score,
            "grade":     _grade(overall_score),
            "rule":      rule_score,
            "adherence": adherence_score,
        },
        "insights": insights,
        "income_analysis": {
            "total_income":  total_income,
            "total_spent":   total_spent,
            "unspent_pct":   income_unspent_pct,
            "score":         income_score,
            "grade":         _grade(income_score),
            "buckets": {
                name: {
                    "assigned":     buckets[name]["assigned"],
                    "spent":        buckets[name]["spent"],
                    "available":    buckets[name]["available"],
                    "value":        (
                        buckets["savings"]["assigned"]
                        if name == "savings"
                        else buckets[name]["spent"]
                    ),
                    "measure":      "assigned" if name == "savings" else "spent",
                    "pct_of_income": income_buckets[name],
                    "target_pct":   round(
                        {"needs": needs_t, "wants": wants_t, "savings": savings_t}[name], 2
                    ),
                    "rule_score":   round(income_rule_scores[name], 1),
                }
                for name in ("needs", "wants", "savings")
            },
        },
        "over_budget_categories": sorted(
            over_budget_categories,
            key=lambda c: c["overspend"],
            reverse=True,
        ),
    }
