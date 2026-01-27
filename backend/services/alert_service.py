from datetime import date
from typing import List, Optional
from sqlalchemy.orm import Session, joinedload

from backend.models import AlertRule, BudgetMonth, Category


def get_budget_alerts(
    db: Session,
    month_date: date,
    include_unconfigured: bool = True
) -> List[dict]:
    rules = db.query(AlertRule).filter(
        AlertRule.rule_type == "budget_threshold",
        AlertRule.is_active == True
    ).all()

    rules_by_category = {rule.category_id: rule for rule in rules if rule.category_id}

    budgets = db.query(BudgetMonth).options(
        joinedload(BudgetMonth.category).joinedload(Category.category_group),
        joinedload(BudgetMonth.currency)
    ).filter(BudgetMonth.month == month_date).all()

    alerts = []
    for budget in budgets:
        category = budget.category
        if not category or not category.category_group or category.category_group.is_income:
            continue

        rule = rules_by_category.get(budget.category_id)
        if not rule and not include_unconfigured:
            continue

        threshold_percent = rule.threshold_percent if rule else 1.0
        assigned = budget.assigned or 0.0
        activity = budget.activity or 0.0
        spent = abs(activity) if activity < 0 else 0.0
        threshold_amount = assigned * threshold_percent

        is_triggered = spent > threshold_amount or (budget.available or 0.0) < 0
        if not is_triggered:
            continue

        alerts.append({
            "rule_id": rule.id if rule else None,
            "category_id": budget.category_id,
            "category_name": category.name,
            "month": budget.month.isoformat() if budget.month else None,
            "currency": budget.currency.to_dict() if budget.currency else None,
            "assigned": assigned,
            "spent": spent,
            "available": budget.available,
            "threshold_percent": threshold_percent,
            "threshold_amount": threshold_amount
        })

    return alerts
