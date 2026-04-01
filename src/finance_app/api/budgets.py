"""
Budgets API endpoints - Multi-moneda con rollover manual
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import date
from typing import Optional

from finance_app.database import get_db
from finance_app.services.budget_service import (
    get_month_budget,
    assign_money_to_category,
    get_budget_overview,
    get_assigned_totals_by_currency,
    calculate_available,
    get_spent_transactions_to_date,
    get_category_budget_history
)
from finance_app.models import BudgetMonth, Currency, Category

router = APIRouter()


class BudgetAssignment(BaseModel):
    """Schema para asignar presupuesto a una categoría"""
    category_id: int
    amount: float
    month: date
    currency_code: str = 'COP'
    rollover_type: Optional[str] = None  # 'accumulate' o 'reset' (opcional, actualiza categoría)


class CoverOverspendingRequest(BaseModel):
    """Schema para cubrir exceso de gasto entre categorías"""
    source_category_id: int
    target_category_id: int
    amount: float
    currency_code: str = 'COP'
    month: date


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


@router.get("/spent-transactions")
def spent_transactions(
    year: Optional[int] = None,
    month: Optional[int] = None,
    currency_code: str = 'COP',
    db: Session = Depends(get_db)
):
    """Get transactions used to calculate 'Gastado este mes'."""
    if year and month:
        month_date = date(year, month, 1)
    else:
        today = date.today()
        month_date = date(today.year, today.month, 1)

    currency = db.query(Currency).filter_by(code=currency_code).first()
    if not currency:
        return {"error": "Currency not found"}

    return get_spent_transactions_to_date(db, month_date, currency.id)


@router.get("/month/{year}/{month}")
def get_budget(year: int, month: int, currency_code: str = 'COP', db: Session = Depends(get_db)):
    """Get budget for a specific month"""
    month_date = date(year, month, 1)
    return get_month_budget(db, month_date, currency_code)


@router.get("/category/{category_id}/history")
def category_budget_history(
    category_id: int,
    months: int = 3,
    db: Session = Depends(get_db)
):
    """Historical budget data and transactions for a category over N months."""
    return get_category_budget_history(db, category_id, months)


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


@router.post("/cover-overspending")
def cover_overspending(request: CoverOverspendingRequest, db: Session = Depends(get_db)):
    """
    Cover overspending by moving available funds from source to target category.
    Does NOT modify 'assigned' for either category.
    Creates two internal transactions (expense in source, income in target) on the
    same budget account so the account balance stays neutral.
    """
    from finance_app.models import Transaction, Account

    currency = db.query(Currency).filter_by(code=request.currency_code).first()
    if not currency:
        return {"error": "Currency not found"}

    source_cat = db.query(Category).get(request.source_category_id)
    target_cat = db.query(Category).get(request.target_category_id)
    if not source_cat or not target_cat:
        return {"error": "Category not found"}

    # Get a budget account to use for the internal transaction
    budget_account = db.query(Account).filter(
        Account.is_budget == True,
        Account.is_closed == False,
        Account.currency_id == currency.id
    ).first()

    if not budget_account:
        return {"error": "No budget account found for this currency"}

    amt = abs(request.amount)

    # Create expense transaction in source category (reduces its available)
    source_tx = Transaction(
        date=request.month,
        amount=-amt,
        account_id=budget_account.id,
        category_id=request.source_category_id,
        currency_id=currency.id,
        original_amount=-amt,
        original_currency_id=currency.id,
        memo=f"Cubrir exceso: {target_cat.name}",
        is_adjustment=True,
    )
    db.add(source_tx)

    # Create income transaction in target category (increases its available)
    target_tx = Transaction(
        date=request.month,
        amount=amt,
        account_id=budget_account.id,
        category_id=request.target_category_id,
        currency_id=currency.id,
        original_amount=amt,
        original_currency_id=currency.id,
        memo=f"Cubierto desde: {source_cat.name}",
        is_adjustment=True,
    )
    db.add(target_tx)

    db.commit()

    # Recalculate available for both categories
    month_date = request.month
    source_budgets = db.query(BudgetMonth).filter_by(
        category_id=request.source_category_id,
        month=month_date,
        currency_id=currency.id
    ).all()
    target_budgets = db.query(BudgetMonth).filter_by(
        category_id=request.target_category_id,
        month=month_date,
        currency_id=currency.id
    ).all()

    for b in source_budgets + target_budgets:
        calculate_available(db, b)

    db.commit()

    return {"success": True, "amount": request.amount, "currency_code": request.currency_code}


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
