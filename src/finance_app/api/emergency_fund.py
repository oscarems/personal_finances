"""
Emergency Fund API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
from datetime import date

from finance_app.database import get_db
from finance_app.models import Category, CategoryGroup
from finance_app.services.emergency_fund_service import (
    calculate_emergency_coverage,
    get_monthly_essential_expenses,
    get_emergency_funds
)

router = APIRouter()


# Pydantic schemas
class CategoryFlagUpdate(BaseModel):
    """Schema for updating emergency fund flags on a category"""
    is_essential: Optional[bool] = None
    is_emergency_fund: Optional[bool] = None


class EmergencyCoverageResponse(BaseModel):
    """Response schema for emergency coverage calculation"""
    months_coverage: float
    emergency_funds_total: float
    essential_expenses_total: float
    currency_code: str
    status: str
    recommendation: str
    funds_detail: dict
    expenses_detail: dict


@router.get("/coverage")
def get_emergency_coverage(
    month: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Calcula la cobertura de emergencia (cuántos meses de gastos esenciales
    están cubiertos por los fondos de emergencia).

    Query params:
    - month: Mes en formato YYYY-MM-DD (opcional, default: mes actual)
    - currency_id: ID de la moneda objetivo (default: 1 = COP)

    Returns:
        EmergencyCoverageResponse con detalles de cobertura
    """
    month_date = None
    if month:
        try:
            month_date = date.fromisoformat(month)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM-DD")

    coverage = calculate_emergency_coverage(db, month_date, currency_id)
    return coverage


@router.get("/expenses")
def get_essential_monthly_expenses(
    month: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Obtiene el total de gastos esenciales mensuales.

    Query params:
    - month: Mes en formato YYYY-MM-DD (opcional, default: mes actual)
    - currency_id: ID de la moneda objetivo (default: 1 = COP)
    """
    month_date = date.today().replace(day=1)
    if month:
        try:
            month_date = date.fromisoformat(month)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM-DD")

    expenses = get_monthly_essential_expenses(db, month_date, currency_id)
    return expenses


@router.get("/funds")
def get_emergency_fund_balances(
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Obtiene el total de fondos de emergencia disponibles.

    Query params:
    - currency_id: ID de la moneda objetivo (default: 1 = COP)
    """
    funds = get_emergency_funds(db, currency_id)
    return funds


@router.get("/categories")
def get_categories_with_flags(db: Session = Depends(get_db)):
    """
    Obtiene todas las categorías con sus flags de emergencia.

    Returns:
        Lista de categorías con campos:
        - id, name, category_group_name
        - is_essential: Si es un gasto esencial
        - is_emergency_fund: Si es un fondo de emergencia
        - rollover_type: 'accumulate' o 'reset'
    """
    categories = db.query(Category).filter_by(is_hidden=False).all()

    return [
        {
            'id': cat.id,
            'name': cat.name,
            'category_group_id': cat.category_group_id,
            'category_group_name': cat.category_group.name if cat.category_group else "",
            'is_essential': cat.is_essential or False,
            'is_emergency_fund': cat.is_emergency_fund or False,
            'rollover_type': cat.rollover_type or 'reset',
            'is_income': cat.category_group.is_income if cat.category_group else False
        }
        for cat in categories
    ]


@router.patch("/categories/{category_id}")
def update_category_flags(
    category_id: int,
    flags: CategoryFlagUpdate,
    db: Session = Depends(get_db)
):
    """
    Actualiza los flags de emergencia de una categoría.

    Args:
        category_id: ID de la categoría a actualizar
        flags: Objeto con is_essential y/o is_emergency_fund

    Returns:
        Categoría actualizada
    """
    category = db.query(Category).get(category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Actualizar solo los campos proporcionados
    if flags.is_essential is not None:
        category.is_essential = flags.is_essential

    if flags.is_emergency_fund is not None:
        category.is_emergency_fund = flags.is_emergency_fund

    db.commit()
    db.refresh(category)

    return {
        'id': category.id,
        'name': category.name,
        'is_essential': category.is_essential,
        'is_emergency_fund': category.is_emergency_fund,
        'message': 'Category updated successfully'
    }


@router.get("/debug")
def debug_emergency_fund(db: Session = Depends(get_db)):
    """
    Endpoint de debug para diagnosticar problemas con el cálculo.

    Returns información detallada sobre:
    - Categorías marcadas como esenciales
    - Categorías marcadas como fondos de emergencia
    - Presupuestos disponibles para cada una
    """
    from finance_app.models import BudgetMonth

    # Categorías esenciales
    essential_cats = db.query(Category).filter(Category.is_essential == True).all()
    essential_data = []
    for cat in essential_cats:
        budgets = db.query(BudgetMonth).filter(
            BudgetMonth.category_id == cat.id
        ).order_by(BudgetMonth.month.desc()).limit(3).all()

        essential_data.append({
            'id': cat.id,
            'name': cat.name,
            'is_essential': cat.is_essential,
            'recent_budgets': [
                {
                    'month': str(b.month),
                    'assigned': b.assigned,
                    'currency_id': b.currency_id
                } for b in budgets
            ]
        })

    # Categorías fondos de emergencia
    emergency_cats = db.query(Category).filter(Category.is_emergency_fund == True).all()
    emergency_data = []
    for cat in emergency_cats:
        budgets = db.query(BudgetMonth).filter(
            BudgetMonth.category_id == cat.id
        ).order_by(BudgetMonth.month.desc()).limit(3).all()

        emergency_data.append({
            'id': cat.id,
            'name': cat.name,
            'is_emergency_fund': cat.is_emergency_fund,
            'rollover_type': cat.rollover_type,
            'recent_budgets': [
                {
                    'month': str(b.month),
                    'available': b.available,
                    'assigned': b.assigned,
                    'currency_id': b.currency_id
                } for b in budgets
            ]
        })

    return {
        'essential_categories': essential_data,
        'emergency_fund_categories': emergency_data,
        'total_essential_marked': len(essential_cats),
        'total_emergency_marked': len(emergency_cats)
    }
