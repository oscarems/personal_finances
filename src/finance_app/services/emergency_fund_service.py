"""
Emergency Fund Service - Calculates essential expense coverage.
"""
from datetime import date
from dateutil.relativedelta import relativedelta
from sqlalchemy import and_
from sqlalchemy.orm import Session, joinedload
from finance_app.models import Category, BudgetMonth, Currency
from finance_app.services.exchange_rate_service import convert_currency


def get_monthly_essential_expenses(db: Session, month_date: date, target_currency_id: int = 1):
    """
    Calculate total monthly essential expenses for a given month.

    If no budget exists for the specified month, falls back to the most recent
    month with an assigned budget to produce an estimate.

    Args:
        db: Database session.
        month_date: Month to calculate (first day of the month).
        target_currency_id: Target currency for conversion (default: COP=1).

    Returns:
        dict: {
            'total': float,  # Total in target currency
            'currency_code': str,  # Currency code
            'categories': [  # List of essential categories
                {
                    'id': int,
                    'name': str,
                    'assigned': float,  # Assigned in original currency
                    'assigned_converted': float,  # Converted assigned amount
                    'currency_code': str
                }
            ]
        }
    """
    # Obtener todas las categorías marcadas como esenciales
    essential_categories = db.query(Category).filter(
        Category.is_essential == True
    ).all()

    if not essential_categories:
        return {
            'total': 0.0,
            'currency_code': 'COP',
            'categories': []
        }

    target_currency = db.query(Currency).get(target_currency_id)

    total = 0.0
    categories_data = []

    for category in essential_categories:
        # Primero intentar obtener presupuesto del mes solicitado
        budgets = db.query(BudgetMonth).options(
            joinedload(BudgetMonth.currency)
        ).filter(
            BudgetMonth.category_id == category.id,
            BudgetMonth.month == month_date
        ).all()

        # Si no hay presupuesto para el mes actual, buscar el mes más reciente
        if not budgets or all(not b.assigned or b.assigned <= 0 for b in budgets):
            budgets = db.query(BudgetMonth).options(
                joinedload(BudgetMonth.currency)
            ).filter(
                BudgetMonth.category_id == category.id,
                BudgetMonth.assigned > 0
            ).order_by(BudgetMonth.month.desc()).limit(10).all()

        category_total = 0.0

        for budget in budgets:
            if budget.assigned and budget.assigned > 0:
                # Convertir a moneda objetivo
                budget_currency_code = budget.currency.code if budget.currency else 'COP'
                target_currency_code = target_currency.code if target_currency else 'COP'

                converted = convert_currency(
                    budget.assigned,
                    budget_currency_code,
                    target_currency_code,
                    db,
                    month_date
                )
                category_total += converted

                categories_data.append({
                    'id': category.id,
                    'name': category.name,
                    'assigned': budget.assigned,
                    'assigned_converted': converted,
                    'currency_code': budget_currency_code
                })
                # Solo tomar el primer presupuesto encontrado (el más reciente)
                break

        total += category_total

    return {
        'total': round(total, 2),
        'currency_code': target_currency.code if target_currency else 'COP',
        'categories': categories_data
    }


def get_emergency_funds(db: Session, target_currency_id: int = 1):
    """
    Calculate the total available emergency funds.

    Emergency funds are categories marked with is_emergency_fund=True
    that have rollover_type='accumulate' (savings).

    Args:
        db: Database session.
        target_currency_id: Target currency for conversion (default: COP=1).

    Returns:
        dict: {
            'total': float,  # Total in target currency
            'currency_code': str,  # Currency code
            'funds': [  # List of funds
                {
                    'id': int,
                    'name': str,
                    'balance': float,  # Balance in original currency
                    'balance_converted': float,  # Converted balance
                    'currency_code': str
                }
            ]
        }
    """
    # Obtener todas las categorías marcadas como fondos de emergencia
    emergency_categories = db.query(Category).filter(
        Category.is_emergency_fund == True
    ).all()

    if not emergency_categories:
        return {
            'total': 0.0,
            'currency_code': 'COP',
            'funds': []
        }

    target_currency = db.query(Currency).get(target_currency_id)
    today = date.today()

    total = 0.0
    funds_data = []

    for category in emergency_categories:
        # Obtener el balance actual de cada fondo (último mes con presupuesto)
        latest_budgets = db.query(BudgetMonth).options(
            joinedload(BudgetMonth.currency)
        ).filter(
            BudgetMonth.category_id == category.id
        ).order_by(BudgetMonth.month.desc()).all()

        # Agrupar por moneda y obtener el balance más reciente
        currency_balances = {}
        for budget in latest_budgets:
            currency_id = budget.currency_id
            if currency_id not in currency_balances:
                # Usar available del budget más reciente
                balance = budget.available or 0.0

                # Si es negativo, usar 0
                if balance < 0:
                    balance = 0.0

                currency_balances[currency_id] = {
                    'balance': balance,
                    'currency': budget.currency
                }

        # Convertir y sumar todos los balances
        for currency_id, data in currency_balances.items():
            balance = data['balance']
            if balance > 0:
                source_currency_code = data['currency'].code if data['currency'] else 'COP'
                target_currency_code = target_currency.code if target_currency else 'COP'

                converted = convert_currency(
                    balance,
                    source_currency_code,
                    target_currency_code,
                    db,
                    today
                )
                total += converted

                funds_data.append({
                    'id': category.id,
                    'name': category.name,
                    'balance': balance,
                    'balance_converted': converted,
                    'currency_code': source_currency_code
                })

    return {
        'total': round(total, 2),
        'currency_code': target_currency.code if target_currency else 'COP',
        'funds': funds_data
    }


def calculate_emergency_coverage(db: Session, month_date: date = None, target_currency_id: int = 1):
    """
    Calculate how many months of coverage the user has with their emergency funds.

    Formula: Months = Total Emergency Funds / Monthly Essential Expenses

    Args:
        db: Database session.
        month_date: Month to use for expense calculation (default: current month).
        target_currency_id: Target currency (default: COP=1).

    Returns:
        dict: {
            'months_coverage': float,  # Number of months of coverage
            'emergency_funds_total': float,  # Total funds
            'essential_expenses_total': float,  # Total essential expenses
            'currency_code': str,  # Currency code
            'status': str,  # 'excellent', 'good', 'fair', 'poor', 'critical'
            'recommendation': str  # Recommendation based on coverage
        }
    """
    if month_date is None:
        month_date = date.today().replace(day=1)

    # Obtener fondos de emergencia
    funds = get_emergency_funds(db, target_currency_id)
    funds_total = funds['total']

    # Obtener gastos esenciales
    expenses = get_monthly_essential_expenses(db, month_date, target_currency_id)
    expenses_total = expenses['total']

    # Calcular meses de cobertura
    if expenses_total > 0:
        months_coverage = funds_total / expenses_total
    else:
        months_coverage = 0.0 if funds_total == 0 else float('inf')

    # Determinar estado y recomendación
    if months_coverage >= 6:
        status = 'excellent'
        recommendation = '¡Excelente! Tienes 6+ meses de cobertura. Tu fondo de emergencia está bien establecido.'
    elif months_coverage >= 3:
        status = 'good'
        recommendation = 'Bien. Tienes 3-6 meses de cobertura. Considera aumentarlo a 6 meses para mayor seguridad.'
    elif months_coverage >= 1:
        status = 'fair'
        recommendation = 'Aceptable. Tienes 1-3 meses. Se recomienda tener al menos 3-6 meses de gastos esenciales.'
    elif months_coverage > 0:
        status = 'poor'
        recommendation = 'Crítico. Tienes menos de 1 mes de cobertura. Prioriza construir tu fondo de emergencia.'
    else:
        status = 'critical'
        if expenses_total == 0:
            recommendation = 'Marca tus gastos esenciales para calcular la cobertura necesaria.'
        else:
            recommendation = 'Sin fondos. Necesitas empezar a construir tu fondo de emergencia urgentemente.'

    target_currency = db.query(Currency).get(target_currency_id)

    return {
        'months_coverage': round(months_coverage, 2) if months_coverage != float('inf') else 999.99,
        'emergency_funds_total': funds_total,
        'essential_expenses_total': expenses_total,
        'currency_code': target_currency.code if target_currency else 'COP',
        'status': status,
        'recommendation': recommendation,
        'funds_detail': funds,
        'expenses_detail': expenses
    }
