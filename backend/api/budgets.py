"""
Budget API endpoints - YNAB style
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date
from pydantic import BaseModel

from backend.database import get_db
from backend.models import BudgetMonth, Category, CategoryGroup, Currency
from backend.services.budget_service import (
    get_month_budget,
    assign_money_to_category,
    get_budget_overview
)

router = APIRouter()


# Pydantic schemas
class BudgetAssign(BaseModel):
    category_id: int
    amount: float
    month: date  # First day of month
    currency_code: str = "COP"


@router.get("/month/{year}/{month}")
def get_budget_for_month(
    year: int,
    month: int,
    currency_code: str = "COP",
    db: Session = Depends(get_db)
):
    """Get budget for a specific month"""
    month_date = date(year, month, 1)
    budget_data = get_month_budget(month_date, currency_code)
    return budget_data


@router.get("/current")
def get_current_budget(
    currency_code: str = "COP",
    db: Session = Depends(get_db)
):
    """Get budget for current month"""
    return get_budget_overview(currency_code)


@router.post("/assign")
def assign_budget(
    assignment: BudgetAssign,
    db: Session = Depends(get_db)
):
    """Assign money to a category"""
    currency = db.query(Currency).filter_by(code=assignment.currency_code).first()
    if not currency:
        return {"error": "Currency not found"}

    budget = assign_money_to_category(
        assignment.category_id,
        assignment.month,
        currency.id,
        assignment.amount
    )

    return budget.to_dict()
