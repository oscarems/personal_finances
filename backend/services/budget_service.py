"""
Budget service - YNAB style "Give every dollar a job"
"""
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, extract
from sqlalchemy.orm import Session
from backend.models import BudgetMonth, Category, CategoryGroup, Transaction, Account, Currency
from backend.services.transaction_service import get_monthly_activity
from backend.services.exchange_rate_service import get_current_exchange_rate, convert_currency


def get_or_create_budget_month(db: Session, category_id, month_date, currency_id):
    """
    Get or create budget entry for a specific month and category
    Args:
        db: Database session
        category_id: Category ID
        month_date: First day of month (date object)
        currency_id: Currency ID
    """
    budget = db.query(BudgetMonth).filter_by(
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
        db.add(budget)
        db.commit()

    return budget


def assign_money_to_category(db: Session, category_id, month_date, currency_id, amount):
    """
    Assign money to a category for a specific month (YNAB: budgeted column)
    """
    budget = get_or_create_budget_month(db, category_id, month_date, currency_id)
    budget.assigned = amount
    calculate_available(db, budget)
    db.commit()
    return budget


def calculate_available(db: Session, budget_month):
    """
    Calculate available amount for a budget month
    For 'accumulate' categories: Available = Assigned - Activity + Previous month's available
    For 'reset' categories: Available = Assigned - Activity (previous month ignored)
    """
    # Get category to check rollover type
    category = db.query(Category).get(budget_month.category_id)

    # Get activity from transactions
    month = budget_month.month.month
    year = budget_month.month.year

    activity = get_monthly_activity(
        db,
        budget_month.category_id,
        month,
        year,
        budget_month.currency_id
    )

    budget_month.activity = activity

    # Get previous month's available (only for 'accumulate' categories)
    prev_available = 0.0

    if category and category.rollover_type == 'accumulate':
        prev_month_date = budget_month.month - relativedelta(months=1)
        prev_budget = db.query(BudgetMonth).filter_by(
            category_id=budget_month.category_id,
            month=prev_month_date,
            currency_id=budget_month.currency_id
        ).first()

        if prev_budget:
            prev_available = prev_budget.available

    # Available = assigned - activity (negative for expenses) + previous available (if accumulate)
    # activity is negative for expenses, so we add it
    budget_month.available = budget_month.assigned + activity + prev_available

    return budget_month


def get_month_budget(db: Session, month_date, currency_code='COP'):
    """
    Get complete budget for a specific month
    Returns all categories with their budget data
    """
    currency = db.query(Currency).filter_by(code=currency_code).first()
    if not currency:
        return None

    # Get all category groups with categories
    groups = db.query(CategoryGroup).order_by(CategoryGroup.sort_order).all()

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

            # Get budgets for this category in ALL currencies
            all_budgets = db.query(BudgetMonth).filter_by(
                category_id=category.id,
                month=month_date
            ).all()

            # If no budgets exist yet, create one for the selected currency
            if not all_budgets:
                budget = get_or_create_budget_month(db, category.id, month_date, currency.id)
                all_budgets = [budget]

            # Sum all budgets, converting to target currency
            total_assigned = 0.0
            total_activity = 0.0
            total_available = 0.0

            for budget in all_budgets:
                # Recalculate available
                calculate_available(db, budget)
                db.commit()

                # Get budget currency
                budget_currency = db.query(Currency).get(budget.currency_id)

                # Convert to target currency
                converted_assigned = convert_currency(
                    amount=budget.assigned,
                    from_currency=budget_currency.code,
                    to_currency=currency.code,
                    db=db
                )
                converted_activity = convert_currency(
                    amount=budget.activity,
                    from_currency=budget_currency.code,
                    to_currency=currency.code,
                    db=db
                )
                converted_available = convert_currency(
                    amount=budget.available,
                    from_currency=budget_currency.code,
                    to_currency=currency.code,
                    db=db
                )

                total_assigned += converted_assigned
                total_activity += converted_activity
                total_available += converted_available

            cat_data = {
                'category_id': category.id,
                'category_name': category.name,
                'assigned': total_assigned,
                'activity': total_activity,
                'available': total_available,
                'target_amount': category.target_amount,
                'rollover_type': category.rollover_type  # 'accumulate' or 'reset'
            }

            group_data['categories'].append(cat_data)

            # Update totals (excluding income)
            if not group.is_income:
                budget_data['totals']['assigned'] += total_assigned
                budget_data['totals']['activity'] += abs(total_activity)
                budget_data['totals']['available'] += total_available

        budget_data['groups'].append(group_data)

    # Calculate "Ready to Assign" - money not assigned to any category
    budget_data['ready_to_assign'] = calculate_ready_to_assign(db, month_date, currency.id)

    return budget_data


def calculate_ready_to_assign(db: Session, month_date, currency_id):
    """
    Calculate money available to assign (dinero sin objetivo)
    = Total en TODAS las cuentas (convertido a moneda seleccionada)
      - Total asignado en TODAS las monedas (convertido a moneda seleccionada)

    Esto representa el dinero que tienes en tus cuentas pero que NO tiene
    una categoría/objetivo asignado todavía.

    IMPORTANTE: Considera TODAS las monedas, convirtiendo todo a la moneda seleccionada
    """
    # Get target currency
    target_currency = db.query(Currency).get(currency_id)

    # Get ALL budget accounts (todas las monedas)
    all_accounts = db.query(Account).filter_by(
        is_closed=False,
        is_budget=True  # Only budget accounts (not tracking accounts)
    ).all()

    # Convert all account balances to target currency
    total_in_accounts = 0.0
    for acc in all_accounts:
        converted_balance = convert_currency(
            amount=acc.balance,
            from_currency=acc.currency.code,
            to_currency=target_currency.code,
            db=db
        )
        total_in_accounts += converted_balance

    # Get ALL budget assignments this month (todas las monedas)
    all_budgets_this_month = db.query(BudgetMonth).filter_by(
        month=month_date
    ).all()

    # Convert all assignments to target currency
    total_assigned = 0.0
    for budget in all_budgets_this_month:
        budget_currency = db.query(Currency).get(budget.currency_id)
        converted_assigned = convert_currency(
            amount=budget.assigned,
            from_currency=budget_currency.code,
            to_currency=target_currency.code,
            db=db
        )
        total_assigned += converted_assigned

    # Add money from 'reset' categories from previous month
    # (money that was assigned but not spent returns to Ready to Assign)
    prev_month_date = month_date - relativedelta(months=1)
    prev_budgets = db.query(BudgetMonth).filter_by(
        month=prev_month_date
    ).all()

    rollover_from_reset = 0.0
    for prev_budget in prev_budgets:
        category = db.query(Category).get(prev_budget.category_id)
        if category and category.rollover_type == 'reset':
            # If there's money left over, it returns to Ready to Assign
            if prev_budget.available > 0:
                prev_currency = db.query(Currency).get(prev_budget.currency_id)
                converted_available = convert_currency(
                    amount=prev_budget.available,
                    from_currency=prev_currency.code,
                    to_currency=target_currency.code,
                    db=db
                )
                rollover_from_reset += converted_available

    # Ready to Assign = Money in accounts - Money already assigned + Money from reset categories
    return total_in_accounts - total_assigned + rollover_from_reset


def get_budget_overview(db: Session, currency_code='COP'):
    """
    Get budget overview for current month
    """
    today = date.today()
    month_date = date(today.year, today.month, 1)

    return get_month_budget(db, month_date, currency_code)


def move_to_next_month(db: Session, current_month_date, currency_id):
    """
    Roll over budget to next month (YNAB style)
    Carries over 'available' amounts to next month
    """
    next_month = current_month_date + relativedelta(months=1)

    budgets = db.query(BudgetMonth).filter_by(
        month=current_month_date,
        currency_id=currency_id
    ).all()

    for budget in budgets:
        if budget.available > 0:
            next_budget = get_or_create_budget_month(
                db,
                budget.category_id,
                next_month,
                currency_id
            )
            # The available will be automatically calculated when needed
            db.commit()

    return True
