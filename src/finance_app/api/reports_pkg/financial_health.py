"""
Financial health endpoint.

Evaluates the monthly BUDGET (not actual spending) against a configurable
50/30/20 allocation rule and produces an adherence score that measures how
closely actual spending tracks what was budgeted.

Categorization of budgeted categories:
- savings: rollover_type == 'accumulate' OR is_emergency_fund
- needs  : is_essential
- wants  : everything else (non-income)

The rule targets (needs/wants/savings) are editable via query params so the
frontend can persist custom splits (e.g. 60/20/20) in localStorage.
"""
from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.services.budget_service import get_month_budget
from .common import get_exchange_rate, convert_to_currency
from .income import get_income_total

router = APIRouter()


def _classify(cat: dict) -> str:
    """Map a budgeted category dict to one of needs/wants/savings."""
    if cat.get("rollover_type") == "accumulate":
        return "savings"
    if cat.get("is_essential"):
        return "needs"
    return "wants"


def _rule_bucket_score(actual_pct: float, target_pct: float, bucket: str) -> float:
    """Score a single 50/30/20 bucket (0-100).

    - needs/wants: overshooting the target is bad (over-spending allocation)
    - savings: undershooting is bad, overshooting is good (capped at 100)
    """
    if target_pct <= 0:
        return 100.0
    if bucket == "savings":
        return min(100.0, (actual_pct / target_pct) * 100.0)
    # needs/wants: ideal = at or below target
    if actual_pct <= target_pct:
        return 100.0
    # linear penalty: 0 when we double the target
    over_ratio = (actual_pct - target_pct) / target_pct
    return max(0.0, 100.0 - over_ratio * 100.0)


def _adherence_score_for_category(assigned: float, spent: float) -> float:
    """Score how well actual spending respects a single category's budget.

    - spent <= assigned → 100
    - spent > assigned  → linear penalty, hits 0 at 2x assigned
    """
    if assigned <= 0:
        # No budget set: if nothing spent, it's fine; if spent, it's fully off.
        return 100.0 if spent <= 0 else 0.0
    if spent <= assigned:
        return 100.0
    over_ratio = (spent - assigned) / assigned
    return max(0.0, 100.0 - over_ratio * 100.0)


@router.get("/financial-health")
def get_financial_health(
    month: Optional[str] = None,
    currency_code: str = "COP",
    needs_target: float = Query(50.0, ge=0, le=100),
    wants_target: float = Query(30.0, ge=0, le=100),
    savings_target: float = Query(20.0, ge=0, le=100),
    db: Session = Depends(get_db),
):
    """Return a 50/30/20 + adherence report for the given month."""
    if month:
        year, mo = month.split("-")
        month_date = date(int(year), int(mo), 1)
    else:
        today = date.today()
        month_date = today.replace(day=1)

    budget = get_month_budget(db, month_date, currency_code=currency_code)
    if budget is None:
        return {"error": f"Unknown currency: {currency_code}"}

    # ------------------------------------------------------------------
    # Compute total income from actual transactions
    # ------------------------------------------------------------------
    currency_obj = budget.get("currency", {})
    currency_id = currency_obj.get("id", 1)
    exchange_rate = get_exchange_rate(db)
    month_end = month_date + relativedelta(months=1)
    total_income = get_income_total(
        db, month_date, month_end, currency_id, exchange_rate,
    )

    buckets: dict[str, dict] = {
        "needs":   {"assigned": 0.0, "spent": 0.0, "categories": []},
        "wants":   {"assigned": 0.0, "spent": 0.0, "categories": []},
        "savings": {"assigned": 0.0, "spent": 0.0, "categories": []},
    }

    total_assigned = 0.0
    total_spent = 0.0
    weighted_adherence_num = 0.0
    weighted_adherence_den = 0.0
    over_budget_categories: list[dict] = []

    for group in budget["groups"]:
        if group.get("is_income"):
            continue
        for cat in group["categories"]:
            assigned = float(cat.get("assigned") or 0.0)
            # activity is negative for spending (and 0 / positive for savings rollovers)
            activity = float(cat.get("activity") or 0.0)
            spent = max(0.0, -activity)

            if assigned <= 0 and spent <= 0:
                continue

            bucket_name = _classify(cat)
            b = buckets[bucket_name]
            b["assigned"] += assigned
            b["spent"] += spent
            b["categories"].append({
                "category_id": cat.get("category_id"),
                "category_name": cat.get("category_name"),
                "group_name": group.get("name"),
                "assigned": assigned,
                "spent": spent,
                "remaining": assigned - spent,
                "rollover_type": cat.get("rollover_type"),
                "is_essential": cat.get("is_essential"),
            })

            total_assigned += assigned
            total_spent += spent

            cat_score = _adherence_score_for_category(assigned, spent)
            # weight by assigned when available, otherwise by spent
            weight = assigned if assigned > 0 else spent
            weighted_adherence_num += cat_score * weight
            weighted_adherence_den += weight

            if assigned > 0 and spent > assigned:
                over_budget_categories.append({
                    "category_name": cat.get("category_name"),
                    "group_name": group.get("name"),
                    "assigned": assigned,
                    "spent": spent,
                    "overspend": spent - assigned,
                    "overspend_pct": (spent - assigned) / assigned * 100.0,
                })

    # ------------------------------------------------------------------
    # Compute allocation percentages (of total assigned budget)
    # ------------------------------------------------------------------
    def _pct(value: float) -> float:
        if total_assigned <= 0:
            return 0.0
        return round(value / total_assigned * 100.0, 2)

    for name, b in buckets.items():
        b["pct_of_assigned"] = _pct(b["assigned"])
        # sort categories by assigned desc for the UI
        b["categories"].sort(key=lambda c: c["assigned"], reverse=True)

    # ------------------------------------------------------------------
    # 50/30/20 rule score (based on how the BUDGET is allocated)
    # ------------------------------------------------------------------
    # Normalize targets so they sum to 100 (guarantees a comparable base).
    target_sum = needs_target + wants_target + savings_target
    if target_sum <= 0:
        needs_t, wants_t, savings_t = 50.0, 30.0, 20.0
    else:
        needs_t = needs_target / target_sum * 100.0
        wants_t = wants_target / target_sum * 100.0
        savings_t = savings_target / target_sum * 100.0

    rule_scores = {
        "needs":   _rule_bucket_score(buckets["needs"]["pct_of_assigned"],   needs_t,   "needs"),
        "wants":   _rule_bucket_score(buckets["wants"]["pct_of_assigned"],   wants_t,   "wants"),
        "savings": _rule_bucket_score(buckets["savings"]["pct_of_assigned"], savings_t, "savings"),
    }
    rule_score = round(sum(rule_scores.values()) / 3.0, 1)

    # ------------------------------------------------------------------
    # Budget adherence score (actual vs budgeted, weighted by assignment)
    # ------------------------------------------------------------------
    if weighted_adherence_den > 0:
        adherence_score = round(weighted_adherence_num / weighted_adherence_den, 1)
    else:
        adherence_score = 100.0

    # ------------------------------------------------------------------
    # Income-based 50/30/20 score (actual spending vs total income)
    # ------------------------------------------------------------------
    income_buckets = {}
    income_rule_scores = {}
    if total_income > 0:
        # Savings: measured by what was ASSIGNED (budgeting intention)
        # Needs/Wants: measured by what was actually SPENT
        for name in ("needs", "wants", "savings"):
            value = buckets[name]["assigned"] if name == "savings" else buckets[name]["spent"]
            income_buckets[name] = round(value / total_income * 100.0, 2)
        target_map = {"needs": needs_t, "wants": wants_t, "savings": savings_t}
        for name in ("needs", "wants", "savings"):
            income_rule_scores[name] = _rule_bucket_score(
                income_buckets[name], target_map[name], name,
            )
        income_score = round(sum(income_rule_scores.values()) / 3.0, 1)
        total_used = total_spent + buckets["savings"]["assigned"]
        income_unspent_pct = round(
            (total_income - total_used) / total_income * 100.0, 2,
        )
    else:
        for name in ("needs", "wants", "savings"):
            income_buckets[name] = 0.0
            income_rule_scores[name] = 0.0
        income_score = 0.0
        income_unspent_pct = 0.0

    # ------------------------------------------------------------------
    # Overall score: weighted combination
    # ------------------------------------------------------------------
    overall_score = round(0.6 * adherence_score + 0.4 * rule_score, 1)

    def _grade(score: float) -> str:
        if score >= 90: return "A"
        if score >= 80: return "B"
        if score >= 70: return "C"
        if score >= 60: return "D"
        return "F"

    return {
        "month": month_date.strftime("%Y-%m"),
        "currency": budget.get("currency"),
        "targets": {
            "needs":   round(needs_t,   2),
            "wants":   round(wants_t,   2),
            "savings": round(savings_t, 2),
        },
        "totals": {
            "assigned": total_assigned,
            "spent":    total_spent,
            "remaining": total_assigned - total_spent,
        },
        "buckets": {
            name: {
                "assigned":        b["assigned"],
                "spent":           b["spent"],
                "pct_of_assigned": b["pct_of_assigned"],
                "target_pct":      round(
                    {"needs": needs_t, "wants": wants_t, "savings": savings_t}[name], 2
                ),
                "rule_score":      round(rule_scores[name], 1),
                "categories":      b["categories"],
            }
            for name, b in buckets.items()
        },
        "scores": {
            "overall":   overall_score,
            "grade":     _grade(overall_score),
            "rule":      rule_score,
            "adherence": adherence_score,
        },
        "income_analysis": {
            "total_income": total_income,
            "total_spent": total_spent,
            "unspent_pct": income_unspent_pct,
            "score": income_score,
            "grade": _grade(income_score),
            "buckets": {
                name: {
                    "assigned": buckets[name]["assigned"],
                    "spent": buckets[name]["spent"],
                    "value": buckets[name]["assigned"] if name == "savings" else buckets[name]["spent"],
                    "measure": "assigned" if name == "savings" else "spent",
                    "pct_of_income": income_buckets[name],
                    "target_pct": round(
                        {"needs": needs_t, "wants": wants_t, "savings": savings_t}[name], 2
                    ),
                    "rule_score": round(income_rule_scores[name], 1),
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
