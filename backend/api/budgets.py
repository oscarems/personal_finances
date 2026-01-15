"""
Budgets API endpoints - Multi-moneda con rollover manual
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import date
from typing import Optional

from backend.database import get_db
from backend.services.budget_service import (
    get_month_budget,
    assign_money_to_category,
    get_budget_overview,
    get_assigned_totals_by_currency
)
from backend.models import BudgetMonth, Currency, Category

router = APIRouter()


class BudgetAssignment(BaseModel):
    """Schema para asignar presupuesto a una categoría"""
    category_id: int
    amount: float
    month: date
    currency_code: str = 'COP'
    rollover_type: Optional[str] = None  # 'accumulate' o 'reset' (opcional, actualiza categoría)


@router.get("/current")
def current_budget(currency_code: str = 'COP', db: Session = Depends(get_db)):
    """Get current month budget"""
    return get_budget_overview(db, currency_code)


@router.get("/assigned-totals")
def assigned_totals(year: Optional[int] = None, month: Optional[int] = None, db: Session = Depends(get_db)):
    """Get total assigned by currency for a month"""
    if year and month:
        month_date = date(year, month, 1)
    else:
        today = date.today()
        month_date = date(today.year, today.month, 1)

    return {
        "month": month_date.isoformat(),
        "totals": get_assigned_totals_by_currency(db, month_date)
    }


@router.get("/month/{year}/{month}")
def get_budget(year: int, month: int, currency_code: str = 'COP', db: Session = Depends(get_db)):
    """Get budget for a specific month"""
    month_date = date(year, month, 1)
    return get_month_budget(db, month_date, currency_code)


@router.get("/category/{category_id}/{month}")
def get_category_budgets(category_id: int, month: str, db: Session = Depends(get_db)):
    """
    Obtiene los presupuestos de una categoría para un mes específico en TODAS las monedas.

    GET /api/budgets/category/5/2025-01

    Returns:
        [
            {"currency_code": "COP", "assigned": 800000, ...},
            {"currency_code": "USD", "assigned": 200, ...}
        ]
    """
    # Parsear mes
    year, month_num = month.split('-')
    month_date = date(int(year), int(month_num), 1)

    # Obtener presupuestos en todas las monedas
    budgets = db.query(BudgetMonth).filter_by(
        category_id=category_id,
        month=month_date
    ).all()

    # Obtener información de monedas
    currencies = {c.id: c for c in db.query(Currency).all()}

    return [
        {
            "currency_code": currencies[b.currency_id].code,
            "currency_id": b.currency_id,
            "assigned": b.assigned,
            "activity": b.activity,
            "available": b.available
        }
        for b in budgets
    ]


@router.post("/assign")
def assign_budget(assignment: BudgetAssignment, db: Session = Depends(get_db)):
    """
    Asigna dinero a una categoría para un mes específico.

    Si se proporciona rollover_type, actualiza el comportamiento de la categoría.
    """
    currency = db.query(Currency).filter_by(code=assignment.currency_code).first()
    if not currency:
        return {"error": "Currency not found"}

    # Si se proporciona rollover_type, actualizar la categoría
    if assignment.rollover_type:
        category = db.query(Category).get(assignment.category_id)
        if category:
            category.rollover_type = assignment.rollover_type
            db.commit()

    budget = assign_money_to_category(
        db,
        assignment.category_id,
        assignment.month,
        currency.id,
        assignment.amount
    )

    return {"success": True, "budget": budget.to_dict()}
