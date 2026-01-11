"""
Budget service - YNAB style "Give every dollar a job"
"""
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, extract
from backend.database import db
from backend.models import BudgetMonth, Category, CategoryGroup, Transaction, Account, Currency
from backend.services.transaction_service import get_monthly_activity


def get_or_create_budget_month(category_id, month_date, currency_id):
    """
    Get or create budget entry for a specific month and category
    Args:
        category_id: Category ID
        month_date: First day of month (date object)
        currency_id: Currency ID
    """
    budget = BudgetMonth.query.filter_by(
        category_id=category_id,
        month=month_date,
        currency_id=currency_id
    ).first()

    if not budget:
        budget = BudgetMonth(
            category_id=category_id,
            month=month_date,
            currency_id=currency_id,
            assigned=0.0,
            activity=0.0,
            available=0.0
        )
        db.session.add(budget)
        db.session.commit()

    return budget


def assign_money_to_category(category_id, month_date, currency_id, amount):
    """
    Assign money to a category for a specific month (YNAB: budgeted column)
    """
    budget = get_or_create_budget_month(category_id, month_date, currency_id)
    budget.assigned = amount
    calculate_available(budget)
    db.session.commit()
    return budget


def calculate_available(budget_month):
    """
    Calculate available amount for a budget month
    Available = Assigned - Activity + Previous month's available
    """
    # Get activity from transactions
    month = budget_month.month.month
    year = budget_month.month.year

    activity = get_monthly_activity(
        budget_month.category_id,
        month,
        year,
        budget_month.currency_id
    )

    budget_month.activity = activity

    # Get previous month's available
    prev_month_date = budget_month.month - relativedelta(months=1)
    prev_budget = BudgetMonth.query.filter_by(
        category_id=budget_month.category_id,
        month=prev_month_date,
        currency_id=budget_month.currency_id
    ).first()

    prev_available = prev_budget.available if prev_budget else 0.0

    # Available = assigned - activity (negative) + previous available
    budget_month.available = budget_month.assigned + abs(activity) + prev_available

    return budget_month


def get_month_budget(month_date, currency_code='COP'):
    """
    Get complete budget for a specific month
    Returns all categories with their budget data
    """
    currency = Currency.query.filter_by(code=currency_code).first()
    if not currency:
        return None

    # Get all category groups with categories
    groups = CategoryGroup.query.order_by(CategoryGroup.sort_order).all()

    budget_data = {
        'month': month_date.isoformat(),
        'currency': currency.to_dict(),
        'groups': [],
        'ready_to_assign': 0.0,
        'totals': {
            'assigned': 0.0,
            'activity': 0.0,
            'available': 0.0
        }
    }

    for group in groups:
        group_data = {
            'id': group.id,
            'name': group.name,
            'is_income': group.is_income,
            'categories': []
        }

        for category in group.categories:
            if category.is_hidden:
                continue

            budget = get_or_create_budget_month(category.id, month_date, currency.id)

            # Recalculate available
            calculate_available(budget)
            db.session.commit()

            cat_data = {
                'category_id': category.id,
                'category_name': category.name,
                'assigned': budget.assigned,
                'activity': budget.activity,
                'available': budget.available,
                'target_amount': category.target_amount
            }

            group_data['categories'].append(cat_data)

            # Update totals (excluding income)
            if not group.is_income:
                budget_data['totals']['assigned'] += budget.assigned
                budget_data['totals']['activity'] += abs(budget.activity)
                budget_data['totals']['available'] += budget.available

        budget_data['groups'].append(group_data)

    # Calculate "Ready to Assign" - money not assigned to any category
    budget_data['ready_to_assign'] = calculate_ready_to_assign(month_date, currency.id)

    return budget_data


def calculate_ready_to_assign(month_date, currency_id):
    """
    Calculate money available to assign
    = Total income - Total assigned to categories
    """
    # Get all income for the month
    income_group = CategoryGroup.query.filter_by(is_income=True).first()
    if not income_group:
        return 0.0

    month = month_date.month
    year = month_date.year

    total_income = 0.0
    for category in income_group.categories:
        activity = get_monthly_activity(category.id, month, year, currency_id)
        total_income += abs(activity)  # Income is positive

    # Get total assigned
    budgets = BudgetMonth.query.filter_by(
        month=month_date,
        currency_id=currency_id
    ).all()

    total_assigned = sum(b.assigned for b in budgets)

    return total_income - total_assigned


def get_budget_overview(currency_code='COP'):
    """
    Get budget overview for current month
    """
    today = date.today()
    month_date = date(today.year, today.month, 1)

    return get_month_budget(month_date, currency_code)


def move_to_next_month(current_month_date, currency_id):
    """
    Roll over budget to next month (YNAB style)
    Carries over 'available' amounts to next month
    """
    next_month = current_month_date + relativedelta(months=1)

    budgets = BudgetMonth.query.filter_by(
        month=current_month_date,
        currency_id=currency_id
    ).all()

    for budget in budgets:
        if budget.available > 0:
            next_budget = get_or_create_budget_month(
                budget.category_id,
                next_month,
                currency_id
            )
            # The available will be automatically calculated when needed
            db.session.commit()

    return True
