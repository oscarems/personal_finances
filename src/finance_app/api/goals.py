from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models import Goal, GoalContribution
from finance_app.services.goal_service import calculate_goal_progress

router = APIRouter()


class GoalCreate(BaseModel):
    name: str
    target_amount: float
    target_date: date
    currency_id: int
    linked_account_id: int | None = None
    start_date: date
    start_amount: float = 0.0
    status: str = "active"
    notes: str | None = None


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


@router.post("/{goal_id}/contributions")
def add_contribution(goal_id: int, payload: GoalContributionCreate, db: Session = Depends(get_db)):
    goal = db.query(Goal).get(goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    contribution = GoalContribution(goal_id=goal_id, **payload.dict())
    db.add(contribution)
    db.commit()
    return {"contribution": contribution.to_dict(), "goal": calculate_goal_progress(db, goal)}
