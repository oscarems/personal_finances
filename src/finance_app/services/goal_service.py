from datetime import date
from typing import Dict

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from finance_app.models import Account, Currency, Goal, GoalContribution
from finance_app.services.exchange_rate_service import convert_currency


def _convert_amount(db: Session, amount: float, from_currency_id: int, to_currency_id: int, rate_date: date) -> float:
    """Convert amount between currencies using exchange rate for a given date."""
    if from_currency_id == to_currency_id:
        return amount
    from_currency = db.query(Currency).get(from_currency_id)
    to_currency = db.query(Currency).get(to_currency_id)
    if not from_currency or not to_currency:
        return amount
    return convert_currency(
        amount=amount,
        from_currency=from_currency.code,
        to_currency=to_currency.code,
        db=db,
        rate_date=rate_date,
    )


def calculate_goal_progress(db: Session, goal: Goal, as_of: date | None = None, months_for_projection: int = 3) -> dict:
    """Calculate progress, gap, and projected achievement date for a financial goal.

    Args:
        db: Database session.
        goal: Goal model instance.
        as_of: Reference date (defaults to today).
        months_for_projection: Number of recent months to average for projection.

    Returns:
        Dict with goal data plus current_amount, gap, required_per_month,
        avg_monthly_real, projected_achievement_date, and status.
    """
    as_of = as_of or date.today()
    if goal.linked_account_id:
        account = db.query(Account).get(goal.linked_account_id)
        if account:
            current_amount = _convert_amount(db, account.balance or 0.0, account.currency_id, goal.currency_id, as_of)
            current_amount = max(0.0, current_amount - (goal.start_amount or 0.0))
        else:
            current_amount = 0.0
    else:
        contributions = db.query(GoalContribution).filter(
            GoalContribution.goal_id == goal.id,
            GoalContribution.date <= as_of,
        ).all()
        current_amount = 0.0
        for contribution in contributions:
            current_amount += _convert_amount(
                db,
                contribution.amount,
                contribution.currency_id,
                goal.currency_id,
                contribution.date,
            )

    gap = max(0.0, (goal.target_amount or 0.0) - current_amount)

    months_remaining = max(1, (goal.target_date.year - as_of.year) * 12 + (goal.target_date.month - as_of.month))
    required_per_month = gap / months_remaining if gap > 0 else 0.0

    recent_start = (as_of.replace(day=1) - relativedelta(months=months_for_projection - 1))
    if goal.linked_account_id:
        avg_monthly_real = current_amount / max(1, months_for_projection)
    else:
        recent = db.query(GoalContribution).filter(
            GoalContribution.goal_id == goal.id,
            GoalContribution.date >= recent_start,
            GoalContribution.date <= as_of,
        ).all()
        if recent:
            total_recent = sum(
                _convert_amount(db, c.amount, c.currency_id, goal.currency_id, c.date) for c in recent
            )
            avg_monthly_real = total_recent / max(1, months_for_projection)
        else:
            avg_monthly_real = 0.0

    if gap <= 0:
        projected_date = as_of
    elif avg_monthly_real <= 0:
        projected_date = None
    else:
        months_to_goal = int((gap / avg_monthly_real) + 0.9999)
        projected_date = as_of + relativedelta(months=months_to_goal)

    status = goal.status
    if current_amount >= goal.target_amount:
        status = "achieved"

    return {
        **goal.to_dict(),
        "current_amount": round(current_amount, 2),
        "gap": round(gap, 2),
        "required_per_month": round(required_per_month, 2),
        "monthly_required": round(required_per_month, 2),
        "avg_monthly_real": round(avg_monthly_real, 2),
        "projected_achievement_date": projected_date.isoformat() if projected_date else None,
        "status": status,
    }
