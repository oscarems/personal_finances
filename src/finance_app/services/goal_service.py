from datetime import date
from typing import Dict

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from finance_app.models import Account, Currency, Goal, GoalContribution
from finance_app.services.exchange_rate_service import convert_currency

GOAL_TYPES = (
    "target_balance_by_date",  # Ahorrar X para una fecha
    "needed_for_spending",     # Necesito X para un gasto puntual en fecha
    "monthly_builder",         # Ahorrar un monto fijo cada mes
)


def _convert_amount(db: Session, amount: float, from_currency_id: int, to_currency_id: int, rate_date: date) -> float:
    """Convert amount between currencies using exchange rate for a given date."""
    if from_currency_id == to_currency_id:
        return amount
    from_currency = db.get(Currency, from_currency_id)
    to_currency = db.get(Currency, to_currency_id)
    if not from_currency or not to_currency:
        return amount
    return convert_currency(
        amount=amount,
        from_currency=from_currency.code,
        to_currency=to_currency.code,
        db=db,
        rate_date=rate_date,
    )


def _current_saved(db: Session, goal: Goal, as_of: date) -> float:
    if goal.linked_account_id:
        account = db.get(Account, goal.linked_account_id)
        if account:
            current_amount = _convert_amount(db, account.balance or 0.0, account.currency_id, goal.currency_id, as_of)
            return max(0.0, current_amount - (goal.start_amount or 0.0))
        return 0.0

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
    return current_amount


def _avg_monthly_real(db: Session, goal: Goal, as_of: date, current_amount: float, months_for_projection: int) -> float:
    recent_start = (as_of.replace(day=1) - relativedelta(months=months_for_projection - 1))
    if goal.linked_account_id:
        return current_amount / max(1, months_for_projection)

    recent = db.query(GoalContribution).filter(
        GoalContribution.goal_id == goal.id,
        GoalContribution.date >= recent_start,
        GoalContribution.date <= as_of,
    ).all()
    if not recent:
        return 0.0
    total_recent = sum(
        _convert_amount(db, c.amount, c.currency_id, goal.currency_id, c.date) for c in recent
    )
    return total_recent / max(1, months_for_projection)


def calculate_goal_progress(db: Session, goal: Goal, as_of: date | None = None, months_for_projection: int = 3) -> dict:
    """Calculate progress, gap, and projected achievement date for a financial goal."""
    as_of = as_of or date.today()
    goal_type = goal.goal_type or "target_balance_by_date"
    current_amount = _current_saved(db, goal, as_of)
    gap = max(0.0, (goal.target_amount or 0.0) - current_amount)

    months_remaining = 1
    if goal.target_date:
        months_remaining = max(
            1,
            (goal.target_date.year - as_of.year) * 12 + (goal.target_date.month - as_of.month),
        )

    if goal_type == "monthly_builder":
        # Fixed monthly contribution; target_amount is optional aspirational total
        required_per_month = float(goal.monthly_amount or 0.0)
        if required_per_month <= 0 and gap > 0 and goal.target_date:
            required_per_month = gap / months_remaining
    elif goal_type == "needed_for_spending":
        # Same math as target_by_date: need remaining by deadline for a known expense
        required_per_month = gap / months_remaining if gap > 0 else 0.0
    else:
        # target_balance_by_date (default)
        required_per_month = gap / months_remaining if gap > 0 else 0.0

    avg_monthly_real = _avg_monthly_real(db, goal, as_of, current_amount, months_for_projection)

    if gap <= 0:
        projected_date = as_of
    elif avg_monthly_real <= 0:
        projected_date = None
    else:
        months_to_goal = int((gap / avg_monthly_real) + 0.9999)
        projected_date = as_of + relativedelta(months=months_to_goal)

    status = goal.status
    if goal.target_amount and current_amount >= goal.target_amount:
        status = "achieved"

    on_track = True
    if required_per_month > 0 and gap > 0:
        on_track = avg_monthly_real >= required_per_month * 0.9

    return {
        **goal.to_dict(),
        "goal_type": goal_type,
        "current_amount": round(current_amount, 2),
        "gap": round(gap, 2),
        "required_per_month": round(required_per_month, 2),
        "monthly_required": round(required_per_month, 2),
        "avg_monthly_real": round(avg_monthly_real, 2),
        "projected_achievement_date": projected_date.isoformat() if projected_date else None,
        "on_track": on_track,
        "status": status,
    }
