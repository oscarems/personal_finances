"""
Budgets API endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import date

from backend.database import get_db
from backend.services.budget_service import (
    get_month_budget, assign_money_to_category, get_budget_overview
)

router = APIRouter()


class BudgetAssignment(BaseModel):
    category_id: int
    amount: float
    month: date
    currency_code: str = 'COP'


@router.get("/current")
def current_budget(currency_code: str = 'COP', db: Session = Depends(get_db)):
    """Get current month budget"""
    return get_budget_overview(db, currency_code)


@router.get("/month/{year}/{month}")
def get_budget(year: int, month: int, currency_code: str = 'COP', db: Session = Depends(get_db)):
    """Get budget for a specific month"""
    month_date = date(year, month, 1)
    return get_month_budget(db, month_date, currency_code)


@router.post("/assign")
def assign_budget(assignment: BudgetAssignment, db: Session = Depends(get_db)):
    """Assign money to a category"""
    from backend.models import Currency
    currency = db.query(Currency).filter_by(code=assignment.currency_code).first()
    if not currency:
        return {"error": "Currency not found"}
    
    budget = assign_money_to_category(
        db,
        assignment.category_id,
        assignment.month,
        currency.id,
        assignment.amount
    )
    return {"success": True, "budget": budget.to_dict()}
