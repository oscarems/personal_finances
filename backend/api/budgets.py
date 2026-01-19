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
    get_assigned_totals_by_currency,
    calculate_available
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


@router.post("/recalculate-savings")
def recalculate_savings_budgets(db: Session = Depends(get_db)):
    """
    Recalcula todos los presupuestos de categorías de ahorro (accumulate).

    Este endpoint corrige el problema donde el initial_amount no se aplicó
    correctamente debido a un race condition. Recalcula todos los presupuestos
    en orden cronológico para asegurar que el rollover funcione correctamente.
    """
    from sqlalchemy import distinct

    # Encontrar todas las categorías de ahorro
    savings_categories = db.query(Category).filter(
        Category.rollover_type == 'accumulate'
    ).all()

    results = []

    for category in savings_categories:
        category_result = {
            "category_id": category.id,
            "category_name": category.name,
            "initial_amount": category.initial_amount,
            "currencies": []
        }

        # Obtener todas las monedas usadas para esta categoría
        budget_currencies = db.query(distinct(BudgetMonth.currency_id)).filter(
            BudgetMonth.category_id == category.id
        ).all()

        for (currency_id,) in budget_currencies:
            currency = db.query(Currency).get(currency_id)

            # Obtener todos los presupuestos de esta categoría en esta moneda
            budgets = db.query(BudgetMonth).filter(
                BudgetMonth.category_id == category.id,
                BudgetMonth.currency_id == currency_id
            ).order_by(BudgetMonth.month).all()

            updated_budgets = []

            # Recalcular cada presupuesto en orden cronológico
            for budget in budgets:
                old_available = budget.available

                # Determinar si hay múltiples monedas en este mes
                existing_budgets = db.query(BudgetMonth).filter_by(
                    category_id=category.id,
                    month=budget.month
                ).all()
                has_multiple_currencies = len({b.currency_id for b in existing_budgets}) > 1

                # Recalcular available
                calculate_available(
                    db,
                    budget,
                    include_all_currencies=not has_multiple_currencies
                )

                if old_available != budget.available:
                    updated_budgets.append({
                        "month": budget.month.isoformat(),
                        "old_available": old_available,
                        "new_available": budget.available,
                        "assigned": budget.assigned,
                        "activity": budget.activity
                    })

            if updated_budgets:
                category_result["currencies"].append({
                    "currency_code": currency.code,
                    "budgets_updated": len(updated_budgets),
                    "updates": updated_budgets
                })

        if category_result["currencies"]:
            results.append(category_result)

    # Hacer commit de todos los cambios
    db.commit()

    return {
        "success": True,
        "categories_processed": len(savings_categories),
        "categories_updated": len(results),
        "details": results
    }
