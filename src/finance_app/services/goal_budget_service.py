"""Auto-creates and syncs a budget category whenever a Goal is created or updated."""
from datetime import date

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from finance_app.models import Category, CategoryGroup
from finance_app.services.budget_service import assign_money_to_category

_GOALS_GROUP_NAME = "Metas"


def _get_or_create_goals_group(db: Session) -> CategoryGroup:
    group = db.query(CategoryGroup).filter_by(name=_GOALS_GROUP_NAME).first()
    if not group:
        max_order = db.query(CategoryGroup).count()
        group = CategoryGroup(name=_GOALS_GROUP_NAME, sort_order=max_order + 1, is_income=False)
        db.add(group)
        db.flush()
    return group


def _get_or_create_goal_category(db: Session, goal_name: str, currency_id: int) -> Category:
    group = _get_or_create_goals_group(db)
    category = db.query(Category).filter_by(
        category_group_id=group.id, name=goal_name
    ).first()
    if not category:
        category = Category(
            category_group_id=group.id,
            name=goal_name,
            rollover_type="accumulate",
            target_type="target_balance",
            is_hidden=False,
            initial_currency_id=currency_id,
        )
        db.add(category)
        db.flush()
    return category


def _month_first_day(year: int, month: int) -> date:
    return date(year, month, 1)


def sync_goal_budget_category(
    db: Session,
    goal,
    recalculate: bool = False,
) -> int:
    """Ensure a budget category exists for the goal and assign the monthly quota.

    Creates the "Metas" group and a matching category if needed, then sets
    `assigned` for every month from start_date to target_date (inclusive) to
    the required monthly amount.  Months already overridden by the user are
    skipped unless *recalculate* is True.

    Returns the category_id that was created or reused.
    """
    category = _get_or_create_goal_category(db, goal.name, goal.currency_id)

    amount_needed = max(0.0, (goal.target_amount or 0.0) - (goal.start_amount or 0.0))
    start = goal.start_date.replace(day=1)
    end = goal.target_date.replace(day=1)

    # Count months between start and end (inclusive)
    months_total = (end.year - start.year) * 12 + (end.month - start.month) + 1
    months_total = max(1, months_total)
    monthly_quota = round(amount_needed / months_total, 2)

    current = start
    today_month = date.today().replace(day=1)
    while current <= end:
        # Only assign from current month onwards; past months keep what they had
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
