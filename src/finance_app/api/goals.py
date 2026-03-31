from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from sqlalchemy import func

from finance_app.database import get_db
from finance_app.models import Goal, GoalContribution, BudgetMonth, Currency
from finance_app.services.goal_service import calculate_goal_progress

router = APIRouter()


class GoalCreate(BaseModel):
    name: str
    target_amount: float
    target_date: date
    currency_id: int
    linked_account_id: int | None = None
    category_id: int | None = None
    start_date: date
    start_amount: float = 0.0
    status: str = "active"
    notes: str | None = None


class GoalUpdate(BaseModel):
    name: Optional[str] = None
    target_amount: Optional[float] = None
    target_date: Optional[date] = None
    currency_id: Optional[int] = None
    linked_account_id: Optional[int] = None
    category_id: Optional[int] = None
    start_date: Optional[date] = None
    start_amount: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class GoalContributionCreate(BaseModel):
    date: date
    amount: float
    currency_id: int
    account_id: int | None = None
    transaction_id: int | None = None
    note: str | None = None


@router.get("/")
def list_goals(db: Session = Depends(get_db), months_projection: int = 3):
    goals = db.query(Goal).order_by(Goal.created_at.desc()).all()
    return [calculate_goal_progress(db, goal, months_for_projection=months_projection) for goal in goals]


@router.post("/")
def create_goal(payload: GoalCreate, db: Session = Depends(get_db)):
    if payload.target_amount <= 0:
        raise HTTPException(status_code=400, detail="target_amount must be > 0")
    if payload.target_date <= payload.start_date:
        raise HTTPException(status_code=400, detail="target_date must be after start_date")

    goal = Goal(**payload.dict())
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return calculate_goal_progress(db, goal)


@router.patch("/{goal_id}")
def update_goal(goal_id: int, payload: GoalUpdate, db: Session = Depends(get_db)):
    goal = db.query(Goal).get(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    updates = payload.dict(exclude_unset=True)
    for key, value in updates.items():
        setattr(goal, key, value)

    db.commit()
    db.refresh(goal)
    return calculate_goal_progress(db, goal)


@router.delete("/{goal_id}")
def delete_goal(goal_id: int, db: Session = Depends(get_db)):
    goal = db.query(Goal).get(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    db.query(GoalContribution).filter(GoalContribution.goal_id == goal_id).delete()
    db.delete(goal)
    db.commit()
    return {"deleted": True, "id": goal_id}


@router.post("/{goal_id}/contributions")
def add_contribution(goal_id: int, payload: GoalContributionCreate, db: Session = Depends(get_db)):
    goal = db.query(Goal).get(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    contribution = GoalContribution(goal_id=goal_id, **payload.dict())
    db.add(contribution)
    db.commit()
    return {"contribution": contribution.to_dict(), "goal": calculate_goal_progress(db, goal)}


@router.get("/{goal_id}/progress")
def get_goal_budget_progress(goal_id: int, db: Session = Depends(get_db)):
    """Get goal progress based on BudgetMonth assigned amounts for the goal's linked category."""
    goal = db.query(Goal).get(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    currency = db.query(Currency).get(goal.currency_id)
    currency_code = currency.code if currency else "COP"

    if not goal.category_id:
        return {
            "goal_id": goal.id,
            "goal_name": goal.name,
            "target_amount": goal.target_amount,
            "current_amount": 0,
            "percentage": 0,
            "months_contributed": 0,
            "remaining": goal.target_amount,
            "on_track": False,
            "monthly_budget_assigned": [],
            "currency_code": currency_code,
            "has_category": False,
        }

    budget_rows = (
        db.query(BudgetMonth)
        .filter(
            BudgetMonth.category_id == goal.category_id,
            BudgetMonth.month >= goal.start_date,
        )
        .order_by(BudgetMonth.month)
        .all()
    )

    monthly_budget_assigned = []
    total_assigned = 0.0
    for row in budget_rows:
        assigned = row.assigned or 0.0
        if assigned > 0:
            total_assigned += assigned
            monthly_budget_assigned.append({
                "month": row.month.isoformat(),
                "assigned": round(assigned, 2),
            })

    target = goal.target_amount or 0
    percentage = min(100, round((total_assigned / target) * 100, 1)) if target > 0 else 0
    remaining = max(0, round(target - total_assigned, 2))

    # on_track: check if current pace would meet target by target_date
    today = date.today()
    months_elapsed = max(1, (today.year - goal.start_date.year) * 12 + (today.month - goal.start_date.month))
    months_total = max(1, (goal.target_date.year - goal.start_date.year) * 12 + (goal.target_date.month - goal.start_date.month))
    expected_pct = min(100, (months_elapsed / months_total) * 100)
    on_track = percentage >= expected_pct

    return {
        "goal_id": goal.id,
        "goal_name": goal.name,
        "target_amount": goal.target_amount,
        "current_amount": round(total_assigned, 2),
        "percentage": percentage,
        "months_contributed": len(monthly_budget_assigned),
        "remaining": remaining,
        "on_track": on_track,
        "monthly_budget_assigned": monthly_budget_assigned,
        "currency_code": currency_code,
        "has_category": True,
    }
