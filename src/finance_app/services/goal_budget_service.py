"""Auto-creates and syncs a budget category whenever a Goal is created or updated."""
from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from finance_app.models import Category, CategoryGroup
from finance_app.services.budget_service import assign_money_to_category

_GOALS_GROUP_NAME = "Metas"

_TYPE_TO_CATEGORY_TARGET = {
    "target_balance_by_date": "target_balance",
    "needed_for_spending": "needed_for_spending",
    "monthly_builder": "monthly",
}


def _get_or_create_goals_group(db: Session) -> CategoryGroup:
    group = db.query(CategoryGroup).filter_by(name=_GOALS_GROUP_NAME).first()
    if not group:
        max_order = db.query(CategoryGroup).count()
        group = CategoryGroup(name=_GOALS_GROUP_NAME, sort_order=max_order + 1, is_income=False)
        db.add(group)
        db.flush()
    return group


def _get_or_create_goal_category(db: Session, goal) -> Category:
    group = _get_or_create_goals_group(db)
    category = db.query(Category).filter_by(
        category_group_id=group.id, name=goal.name
    ).first()
    goal_type = getattr(goal, "goal_type", None) or "target_balance_by_date"
    target_type = _TYPE_TO_CATEGORY_TARGET.get(goal_type, "target_balance")
    if not category:
        category = Category(
            category_group_id=group.id,
            name=goal.name,
            rollover_type="accumulate",
            target_type=target_type,
            target_amount=goal.target_amount,
            target_date=goal.target_date,
            is_hidden=False,
            initial_currency_id=goal.currency_id,
        )
        db.add(category)
        db.flush()
    else:
        category.target_type = target_type
        category.target_amount = goal.target_amount
        category.target_date = goal.target_date
        category.name = goal.name
    return category


def sync_goal_budget_category(
    db: Session,
    goal,
    recalculate: bool = False,
) -> int:
    """Ensure a budget category exists for the goal and assign the monthly quota.

    Returns the category_id that was created or reused.
    """
    category = _get_or_create_goal_category(db, goal)
    goal_type = getattr(goal, "goal_type", None) or "target_balance_by_date"

    amount_needed = max(0.0, (goal.target_amount or 0.0) - (goal.start_amount or 0.0))
    start = goal.start_date.replace(day=1)
    end = goal.target_date.replace(day=1) if goal.target_date else start + relativedelta(months=11)

    months_total = (end.year - start.year) * 12 + (end.month - start.month) + 1
    months_total = max(1, months_total)

    if goal_type == "monthly_builder" and goal.monthly_amount and goal.monthly_amount > 0:
        monthly_quota = round(float(goal.monthly_amount), 2)
    else:
        monthly_quota = round(amount_needed / months_total, 2)

    current = start
    today_month = date.today().replace(day=1)
    while current <= end:
        if current >= today_month or recalculate:
            assign_money_to_category(
                db,
                category_id=category.id,
                month_date=current,
                currency_id=goal.currency_id,
                amount=monthly_quota,
            )
        current += relativedelta(months=1)

    db.commit()
    return category.id
