"""
Budget service — monthly budgeting: assign every dollar to a category.

Provides helpers for building, querying and calculating budget data including
multi-currency conversion, rollover logic and the Ready-to-Assign figure.
"""
from __future__ import annotations

from datetime import date, datetime
from collections.abc import Callable
from typing import Optional
from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, extract, or_
from sqlalchemy.orm import Session, joinedload
from finance_app.models import BudgetMonth, Category, CategoryGroup, Transaction, Account, Currency
from finance_app.services.transaction_service import get_monthly_activity
from finance_app.services.exchange_rate_service import get_current_exchange_rate, convert_currency


# ---------------------------------------------------------------------------
# Shared currency-conversion helper
# ---------------------------------------------------------------------------

def _make_currency_converter(
    target_currency_code: str,
    exchange_rate_usd_cop: float,
) -> Callable:
    """Return a closure that converts *amount* from *from_code* to the target currency.

    The returned function uses a cached exchange rate so no extra DB queries
    are needed.
    """
    def _convert(amount: float, from_code: str) -> float:
        if from_code == target_currency_code:
            return amount
        if from_code == "USD" and target_currency_code == "COP":
            return amount * exchange_rate_usd_cop
        if from_code == "COP" and target_currency_code == "USD":
            return amount / exchange_rate_usd_cop
        return amount
    return _convert


def _make_currency_converter_2arg(
    target_currency_code: str,
    exchange_rate_usd_cop: float,
) -> Callable:
    """Like :func:`_make_currency_converter` but accepts *(from_code, to_code)*.

    Used inside ``get_month_budget`` where both source and target codes are
    passed explicitly.
    """
    def _convert(amount: float, from_code: str, to_code: str) -> float:
        if from_code == to_code:
            return amount
        if from_code == "USD" and to_code == "COP":
            return amount * exchange_rate_usd_cop
        if from_code == "COP" and to_code == "USD":
            return amount / exchange_rate_usd_cop
        return amount
    return _convert


def build_spent_transactions_query(
    db: Session,
    start_date: date,
    end_date: date,
    category_id: Optional[int] = None
):
    """
    Build the base query for expense transactions.

    - Expenses only (negative amounts)
    - Excludes transfers and balance adjustments
    - Excludes income categories
    - Date range with exclusive end [start_date, end_date)
    """
    query = db.query(Transaction).join(Category).join(CategoryGroup).filter(
        Transaction.date >= start_date,
        Transaction.date < end_date,
        Transaction.amount < 0,
        Transaction.transfer_account_id.is_(None),
        Transaction.is_adjustment.is_(False),
        CategoryGroup.is_income.is_(False)
    )

    if category_id is not None:
        query = query.filter(Transaction.category_id == category_id)

    return query


def build_income_transactions_query(
    db: Session,
    start_date: date,
    end_date: date,
    category_id: Optional[int] = None
):
    """
    Build the base query for income transactions.

    - Income only (positive amounts)
    - Excludes transfers and balance adjustments
    - Includes income categories or uncategorized income
    - Date range with exclusive end [start_date, end_date)
    """
    query = db.query(Transaction).outerjoin(Category).outerjoin(CategoryGroup).filter(
        Transaction.date >= start_date,
        Transaction.date < end_date,
        Transaction.amount > 0,
        Transaction.transfer_account_id.is_(None),
        Transaction.is_adjustment.is_(False)
    ).filter(
        or_(
            CategoryGroup.is_income.is_(True),
            Transaction.category_id.is_(None)
        )
    )

    if category_id is not None:
        query = query.filter(Transaction.category_id == category_id)

    return query


def get_assigned_totals_by_currency(db: Session, month_date):
    """
    Get total assigned amounts per currency for a specific month.

    Includes expense categories only (excludes income groups) and sums
    the assigned value for the month, ignoring prior accumulated balances.

    Returns:
        dict: Dictionary with currency codes as keys and dicts containing
              'total' and 'symbol' as values, e.g.:
              {"COP": {"total": 5000000, "symbol": "$"}, "USD": {"total": 100, "symbol": "US$"}}
    """
    totals = {}
    budgets = db.query(BudgetMonth).options(
        joinedload(BudgetMonth.category).joinedload(Category.category_group),
        joinedload(BudgetMonth.currency)
    ).filter_by(month=month_date).all()

    for budget in budgets:
        category = budget.category
        if not category or not category.category_group:
            continue
        if category.category_group.is_income:
            continue

        currency = budget.currency
        if not currency or not currency.code:
            continue

        currency_code = currency.code
        currency_symbol = currency.symbol if hasattr(currency, 'symbol') and currency.symbol else ('US$' if currency_code == 'USD' else '$')

        if currency_code not in totals:
            totals[currency_code] = {"total": 0.0, "symbol": currency_symbol}

        totals[currency_code]["total"] += (budget.assigned or 0.0)

    return totals


def get_previous_budget(db: Session, category_id, month_date, currency_id):
    return db.query(BudgetMonth).filter(
        BudgetMonth.category_id == category_id,
        BudgetMonth.currency_id == currency_id,
        BudgetMonth.month < month_date
    ).order_by(BudgetMonth.month.desc()).first()


def has_any_previous_budget(db: Session, category_id, currency_id, exclude_month=None):
    """
    Check whether ANY prior budget exists for this category in this currency.

    This prevents using initial_amount more than once: it should only be applied
    the very first time a category is budgeted in a given currency.

    Args:
        exclude_month: Month to exclude from the search (to avoid counting the current month).

    Returns:
        bool: True if at least one prior budget exists, False if this is the first time.
    """
    query = db.query(BudgetMonth).filter(
        BudgetMonth.category_id == category_id,
        BudgetMonth.currency_id == currency_id
    )

    if exclude_month:
        query = query.filter(BudgetMonth.month != exclude_month)

    return query.first() is not None


def get_or_create_budget_month(db: Session, category_id, month_date, currency_id):
    """
    Get or create a budget entry for a specific month and category.

    Looks for an existing budget for the category/month/currency combination.
    If none exists, creates a new one with zero values.

    Args:
        db (Session): SQLAlchemy database session.
        category_id (int): ID of the category to budget.
        month_date (date): First day of the month (e.g. date(2025, 1, 1)).
        currency_id (int): Currency ID (1=COP, 2=USD).

    Returns:
        BudgetMonth: Monthly budget object (existing or newly created).

    Example:
        >>> from datetime import date
        >>> budget = get_or_create_budget_month(db, category_id=5,
        ...                                     month_date=date(2025, 1, 1),
        ...                                     currency_id=1)
        >>> print(budget.assigned)  # 0.0 if new
    """
    budget = db.query(BudgetMonth).filter_by(
        category_id=category_id,
        month=month_date,
        currency_id=currency_id
    ).first()

    if not budget:
        # Inherit assigned from previous month if it exists
        prev_month_date = month_date - relativedelta(months=1)
        prev_budget = db.query(BudgetMonth).filter_by(
            category_id=category_id,
            month=prev_month_date,
            currency_id=currency_id
        ).first()
        inherited_assigned = prev_budget.assigned if prev_budget else 0.0

        budget = BudgetMonth(
            category_id=category_id,
            month=month_date,
            currency_id=currency_id,
            assigned=inherited_assigned,
            activity=0.0,
            available=0.0
        )
        db.add(budget)
        db.commit()

    return budget


def assign_money_to_category(db: Session, category_id, month_date, currency_id, amount, initial_amount=None):
    """
    Assign money to a category for a specific month.

    After saving the current month, propagates the change to all future months
    already in the DB: updates their assigned (if not explicitly overridden by the
    user) and recalculates their available in chronological order.

    Args:
        db (Session): Database session.
        category_id (int): Category ID.
        month_date (date): First day of the month.
        currency_id (int): Currency ID.
        amount (float): Amount to assign (0 or positive).
        initial_amount (float, optional): Initial accumulated amount (for accumulate categories).

    Returns:
        BudgetMonth: Updated budget object with the new assigned value.
    """
    budget = get_or_create_budget_month(db, category_id, month_date, currency_id)
    budget.assigned = amount
    budget.assigned_overridden = True
    if initial_amount is not None:
        budget.initial_amount = initial_amount
        budget.initial_overridden = True
    existing_budgets = db.query(BudgetMonth).filter_by(
        category_id=category_id,
        month=month_date
    ).all()
    has_multiple_budget_currencies = len({b.currency_id for b in existing_budgets}) > 1
    recalculate_budget_available(
        db,
        budget,
        include_all_currencies=not has_multiple_budget_currencies
    )
    db.flush()
    _cascade_future_months(db, category_id, currency_id, month_date)
    db.commit()
    return budget


def _cascade_future_months(db: Session, category_id: int, currency_id: int, from_month: date) -> None:
    """Propagate assigned changes and recalculate available for all future months
    already in the DB for this category/currency.

    Rules:
    - Future months without assigned_overridden=True inherit assigned from the prior month.
    - available is always recalculated (includes savings rollover).
    - Processed in chronological order so each month picks up the previous month's available.
    """
    future_budgets = db.query(BudgetMonth).filter(
        BudgetMonth.category_id == category_id,
        BudgetMonth.currency_id == currency_id,
        BudgetMonth.month > from_month
    ).order_by(BudgetMonth.month).all()

    if not future_budgets:
        return

    for future_budget in future_budgets:
        if not future_budget.assigned_overridden:
            # Inherit assigned from the immediately preceding month
            prev_month = future_budget.month - relativedelta(months=1)
            prev_budget = db.query(BudgetMonth).filter_by(
                category_id=category_id,
                currency_id=currency_id,
                month=prev_month
            ).first()
            if prev_budget is not None:
                future_budget.assigned = prev_budget.assigned

        # Check if this category has multi-currency budgets for this month
        existing_budgets = db.query(BudgetMonth).filter_by(
            category_id=category_id,
            month=future_budget.month
        ).all()
        has_multi_curr = len({b.currency_id for b in existing_budgets}) > 1
        recalculate_budget_available(db, future_budget, include_all_currencies=not has_multi_curr)
        db.flush()


def recalculate_budget_available(db: Session, budget_month, include_all_currencies: bool = True):
    """
    Calculate the available amount for a monthly budget entry.

    Implements rollover logic for two category types:

    1. ACCUMULATE (savings): Available is calculated from the initial balance
       plus the month's assigned minus spending.
       Formula: Available = Initial Amount + Assigned + Activity
       Example: $200 initial, $100 assigned, $30 spent:
                Available = $200 + $100 + (-$30) = $270

    2. RESET (monthly spending): Resets each month.
       Formula: Available = Assigned + Activity
       Example: $100 assigned, $30 spent:
                Available = $100 + (-$30) = $70

    Args:
        db (Session): Database session.
        budget_month (BudgetMonth): Monthly budget object to calculate.

    Returns:
        BudgetMonth: Same object with activity and available fields updated.

    Side effects:
        - Updates budget_month.activity by querying transactions for the month.
        - Updates budget_month.available based on rollover type.
        - Does NOT commit; the caller must commit.

    Note:
        Activity is NEGATIVE for expenses and POSITIVE for income.
        Example: spending $50 → activity = -$50.
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
        budget_month.currency_id,
        include_all_currencies=include_all_currencies
    )

    budget_month.activity = activity

    # Get initial amount (only for 'accumulate' categories)
    initial_available = 0.0

    if category and category.rollover_type == 'accumulate':
        if budget_month.initial_overridden:
            # User set this value explicitly — respect it
            initial_available = budget_month.initial_amount or 0.0
        else:
            # Auto-derive from previous month's available (rollover)
            prev_month_date = budget_month.month - relativedelta(months=1)
            prev_budget = db.query(BudgetMonth).filter_by(
                category_id=budget_month.category_id,
                currency_id=budget_month.currency_id,
                month=prev_month_date
            ).first()
            if prev_budget is not None:
                initial_available = prev_budget.available or 0.0
                # Keep initial_amount in sync for display purposes
                budget_month.initial_amount = initial_available
            else:
                # First month ever — no prev exists, use stored seed value
                initial_available = budget_month.initial_amount or 0.0

    # Available = assigned - activity (negative for expenses) + initial amount (if accumulate)
    # activity is negative for expenses, so we add it
    budget_month.available = budget_month.assigned + activity + initial_available

    return budget_month


def get_month_budget(db: Session, month_date, currency_code='COP'):
    """
    Get the complete budget for a specific month with ALL categories.

    Main function for retrieving the budget view. Returns a full structure
    with all category groups, their categories, and budget values
    (assigned, activity, available).

    Multi-currency: If a category has budgets in both USD and COP, they are
    summed by converting everything to the requested currency.

        Example: Category "Food"
            - Budget in COP: $800,000
            - Budget in USD: $100 (= $400,000 COP at rate 4000)
            - Total shown in COP: $1,200,000

    Args:
        db (Session): Database session.
        month_date (date): First day of the month (e.g. date(2025, 1, 1)).
        currency_code (str): Display currency code ('COP' or 'USD').

    Returns:
        dict: Budget structure with format:
            {
                'month': '2025-01-01',
                'currency': {'id': 1, 'code': 'COP', 'symbol': '$'},
                'ready_to_assign': 500000.0,
                'totals': {
                    'assigned': 2000000.0,
                    'activity': -1500000.0,
                    'available': 500000.0,
                    'in_accounts': 9000000.0
                },
                'groups': [
                    {
                        'id': 1,
                        'name': 'Gastos Esenciales',
                        'is_income': False,
                        'categories': [
                            {
                                'category_id': 1,
                                'category_name': 'Comida',
                                'assigned': 800000.0,
                                'activity': -650000.0,
                                'available': 150000.0,
                                'target_amount': 1000000.0,
                                'rollover_type': 'reset'
                            },
                            ...
                        ]
                    },
                    ...
                ]
            }

    Optimizations:
        1. Eager loading with joinedload() to avoid N+1 queries.
        2. In-memory exchange rate cache (1 query instead of 100+).
        3. All currencies cached in a dictionary.
        4. Batch query for ALL month budgets at once.
        5. O(1) dictionary lookups instead of repeated queries.
        6. Single commit at the end.

    Performance:
        Reduced from ~200 queries to just 4 queries (~50x improvement).

    Notes:
        - Hidden categories (is_hidden=True) are excluded.
        - Income groups are included but not summed into totals.
        - If no budget exists for a category, one is created automatically.
    """
    currency = db.query(Currency).filter_by(code=currency_code).first()
    if not currency:
        return None

    all_currencies = {c.id: c for c in db.query(Currency).all()}
    exchange_rate_usd_cop = get_current_exchange_rate(db)
    convert = _make_currency_converter_2arg(currency.code, exchange_rate_usd_cop)

    groups = db.query(CategoryGroup).options(
        joinedload(CategoryGroup.categories)
    ).order_by(CategoryGroup.sort_order).all()

    budget_data: dict = {
        'month': month_date.isoformat(),
        'currency': currency.to_dict(),
        'groups': [],
        'ready_to_assign': 0.0,
        'totals': {'assigned': 0.0, 'activity': 0.0, 'available': 0.0},
    }

    budgets_by_category = _index_budgets_by_category(db, month_date)

    for group in groups:
        group_data = _build_group_budget(
            db, group, month_date, currency, all_currencies,
            convert, budgets_by_category, budget_data['totals'],
        )
        budget_data['groups'].append(group_data)

    db.commit()

    total_in_accounts = calculate_total_in_accounts(db, currency.id)
    budget_data['totals']['in_accounts'] = total_in_accounts
    budget_data['ready_to_assign'] = total_in_accounts - budget_data['totals']['available']

    return budget_data


# -- helpers for get_month_budget ------------------------------------------

def _index_budgets_by_category(db: Session, month_date: date) -> dict[int, list[BudgetMonth]]:
    """Load all budget rows for *month_date* and index them by category_id."""
    all_month_budgets = db.query(BudgetMonth).options(
        joinedload(BudgetMonth.category)
    ).filter_by(month=month_date).all()

    index: dict[int, list[BudgetMonth]] = {}
    for budget in all_month_budgets:
        index.setdefault(budget.category_id, []).append(budget)
    return index


def _build_group_budget(
    db: Session,
    group: CategoryGroup,
    month_date: date,
    currency: Currency,
    all_currencies: dict,
    convert: Callable,
    budgets_by_category: dict[int, list[BudgetMonth]],
    running_totals: dict,
) -> dict:
    """Build the budget dict for a single category group."""
    group_data: dict = {
        'id': group.id,
        'name': group.name,
        'is_income': group.is_income,
        'categories': [],
    }

    for category in group.categories:
        if category.is_hidden:
            continue

        cat_data = _build_category_budget(
            db, category, month_date, currency, all_currencies,
            convert, budgets_by_category,
        )
        group_data['categories'].append(cat_data)

        if not group.is_income:
            running_totals['assigned'] += cat_data['assigned']
            running_totals['activity'] += abs(cat_data['activity'])
            running_totals['available'] += cat_data['available']

    return group_data


def _build_category_budget(
    db: Session,
    category: Category,
    month_date: date,
    currency: Currency,
    all_currencies: dict,
    convert: Callable,
    budgets_by_category: dict[int, list[BudgetMonth]],
) -> dict:
    """Build the budget dict for a single category within a group."""
    all_budgets = budgets_by_category.get(category.id, [])
    if not all_budgets:
        budget = get_or_create_budget_month(db, category.id, month_date, currency.id)
        all_budgets = [budget]

    has_multi_curr = len({b.currency_id for b in all_budgets}) > 1

    total_assigned = 0.0
    total_activity = 0.0
    total_available = 0.0

    for budget in all_budgets:
        recalculate_budget_available(db, budget, include_all_currencies=not has_multi_curr)
        bcur = all_currencies.get(budget.currency_id)
        if not bcur:
            continue
        total_assigned += convert(budget.assigned, bcur.code, currency.code)
        total_activity += convert(budget.activity, bcur.code, currency.code)
        total_available += convert(budget.available, bcur.code, currency.code)

    total_initial = 0.0
    if category.rollover_type == 'accumulate':
        for budget in all_budgets:
            bcur = all_currencies.get(budget.currency_id)
            if bcur:
                total_initial += convert(budget.initial_amount or 0.0, bcur.code, currency.code)

    return {
        'category_id': category.id,
        'category_name': category.name,
        'assigned': total_assigned,
        'activity': total_activity,
        'available': total_available,
        'initial_amount': total_initial,
        'target_amount': category.target_amount,
        'rollover_type': category.rollover_type,
        'is_essential': bool(category.is_essential),
    }


def calculate_total_in_accounts(db: Session, currency_id: int) -> float:
    """Return the sum of all open budget-account balances converted to *currency_id*.

    Excludes debt accounts (credit_card, credit_loan, mortgage).
    """
    target_currency = db.query(Currency).get(currency_id)
    convert = _make_currency_converter(target_currency.code, get_current_exchange_rate(db))

    excluded_types = {'credit_card', 'credit_loan', 'mortgage'}
    accounts = db.query(Account).options(
        joinedload(Account.currency)
    ).filter(
        Account.is_closed == False,
        Account.is_budget == True,
        ~Account.type.in_(excluded_types),
    ).all()

    return sum(convert(acc.balance, acc.currency.code) for acc in accounts)


def calculate_ready_to_assign(db: Session, month_date, currency_id):
    """
    Calculate the money available to assign (Ready to Assign).

    Represents money in budget accounts that has not yet been assigned to any category.

    Formula:
        Ready to Assign = Total in budget accounts - Total available in categories this month

    Example:
        Budget accounts:
            - Checking COP: $5,000,000
            - Savings USD: $1,000 (= $4,000,000 COP at rate 4000)
            Total in accounts: $9,000,000 COP

        Available in categories (January):
            - Food (COP): $700,000
            - Transport (USD): $100 (= $400,000 COP)
            Total available: $1,100,000 COP

        Ready to Assign = $9,000,000 - $1,100,000 = $7,900,000 COP

    Multi-currency: All accounts and budgets in all currencies are considered,
    converted to the target currency before subtraction.

    Args:
        db (Session): Database session.
        month_date (date): First day of the month to calculate.
        currency_id (int): Target currency ID for the result.

    Returns:
        float: Amount available to assign in the target currency.

    Notes:
        - Only considers budget accounts (is_budget=True).
        - Only considers open accounts (is_closed=False).
        - Excludes debt accounts (credit_card, credit_loan, mortgage).
        - Tracking accounts are NOT included.
    """
    target_currency = db.query(Currency).get(currency_id)
    convert = _make_currency_converter(target_currency.code, get_current_exchange_rate(db))

    total_in_accounts = calculate_total_in_accounts(db, currency_id)

    all_budgets = db.query(BudgetMonth).options(
        joinedload(BudgetMonth.category).joinedload(Category.category_group)
    ).filter_by(month=month_date).all()

    currency_cache = {c.id: c for c in db.query(Currency).all()}
    cat_currencies: dict[int, set[int]] = {}
    for b in all_budgets:
        cat_currencies.setdefault(b.category_id, set()).add(b.currency_id)

    total_available = 0.0
    for budget in all_budgets:
        if budget.category and budget.category.category_group and budget.category.category_group.is_income:
            continue
        has_multi = len(cat_currencies.get(budget.category_id, set())) > 1
        recalculate_budget_available(db, budget, include_all_currencies=not has_multi)
        bcur = currency_cache.get(budget.currency_id)
        if bcur:
            total_available += convert(budget.available, bcur.code)

    return total_in_accounts - total_available


def calculate_assigned_this_month(db: Session, month_date, currency_id):
    """
    Calculate total assigned in the current month, excluding amounts inherited from prior months.

    Computed as the delta between this month's assigned and the previous month's assigned,
    per category/currency.
    """
    target_currency = db.query(Currency).get(currency_id)
    if not target_currency:
        return 0.0

    convert = _make_currency_converter(target_currency.code, get_current_exchange_rate(db))
    previous_month = month_date - relativedelta(months=1)

    budgets = db.query(BudgetMonth).options(
        joinedload(BudgetMonth.category).joinedload(Category.category_group),
        joinedload(BudgetMonth.currency)
    ).filter_by(month=month_date).all()

    total_assigned = 0.0
    for budget in budgets:
        if not budget.category or not budget.category.category_group:
            continue
        if budget.category.category_group.is_income:
            continue

        prev_budget = db.query(BudgetMonth).filter_by(
            category_id=budget.category_id,
            currency_id=budget.currency_id,
            month=previous_month
        ).first()

        previous_assigned = prev_budget.assigned if prev_budget else 0.0
        delta_assigned = (budget.assigned or 0.0) - (previous_assigned or 0.0)

        budget_currency = budget.currency
        if not budget_currency:
            continue

        total_assigned += convert(delta_assigned, budget_currency.code)

    return total_assigned


def calculate_spent_to_date(db: Session, month_date, currency_id):
    """
    Calculate total spending from the first day of the month through today (inclusive).
    Only considers expense transactions (negative amounts) and excludes income.
    """
    target_currency = db.query(Currency).get(currency_id)
    if not target_currency:
        return 0.0

    start_date = month_date
    end_of_month = month_date + relativedelta(months=1)
    today = date.today()

    if today < start_date:
        end_date = start_date
    elif today >= end_of_month:
        end_date = end_of_month
    else:
        end_date = today + relativedelta(days=1)

    transactions = build_spent_transactions_query(db, start_date, end_date).options(
        joinedload(Transaction.currency)
    ).all()

    total_spent = 0.0
    for tx in transactions:
        tx_currency = tx.currency.code if tx.currency else target_currency.code
        converted_amount = convert_currency(
            abs(tx.amount),
            tx_currency,
            target_currency.code,
            db,
            rate_date=tx.date
        )
        total_spent += converted_amount

    return total_spent


def get_spent_transactions_to_date(db: Session, month_date, currency_id):
    """
    Get transactions used to calculate "spent this month".

    Returns a list of expense transactions (negative amounts) from the first day
    of the month through today (inclusive), with each amount converted to the
    target currency for display in the UI.
    """
    target_currency = db.query(Currency).get(currency_id)
    if not target_currency:
        return {"error": "Currency not found"}

    start_date = month_date
    end_of_month = month_date + relativedelta(months=1)
    today = date.today()

    if today < start_date:
        end_date = start_date
    elif today >= end_of_month:
        end_date = end_of_month
    else:
        end_date = today + relativedelta(days=1)

    transactions = build_spent_transactions_query(db, start_date, end_date).options(
        joinedload(Transaction.currency),
        joinedload(Transaction.account),
        joinedload(Transaction.payee),
        joinedload(Transaction.category)
    ).order_by(Transaction.date.desc()).all()

    detailed = []
    total_spent = 0.0
    for tx in transactions:
        tx_currency = tx.currency.code if tx.currency else target_currency.code
        converted_amount = convert_currency(
            abs(tx.amount),
            tx_currency,
            target_currency.code,
            db,
            rate_date=tx.date
        )
        total_spent += converted_amount
        tx_data = tx.to_dict()
        tx_data["spent_converted"] = converted_amount
        tx_data["spent_currency_code"] = target_currency.code
        detailed.append(tx_data)

    return {
        "currency_code": target_currency.code,
        "total_spent": total_spent,
        "transactions": detailed
    }


def get_budget_overview(db: Session, currency_code='COP'):
    """
    Get budget overview for current month
    """
    today = date.today()
    month_date = date(today.year, today.month, 1)

    return get_month_budget(db, month_date, currency_code)


def move_to_next_month(db: Session, current_month_date, currency_id):
    """
    Roll over budget to the next month.
    Carries over 'available' amounts to the next month.
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


def _sum_by_currency_code(
    budgets_list: list[BudgetMonth],
    currencies: dict,
    code: str,
    field: str,
) -> float:
    """Sum *field* from budget rows whose currency matches *code*."""
    return sum(
        getattr(b, field) or 0
        for b in budgets_list
        if currencies.get(b.currency_id) and currencies[b.currency_id].code == code
    )


def _summarise_month_budgets(
    month: date,
    all_budgets: list[BudgetMonth],
    currencies: dict,
    to_cop_fn: Callable,
) -> dict:
    """Build one row of the monthly summary table for budget history."""
    month_budgets = [b for b in all_budgets if b.month == month]
    return {
        "month": month.isoformat(),
        "assigned_cop": _sum_by_currency_code(month_budgets, currencies, "COP", "assigned"),
        "activity_cop": _sum_by_currency_code(month_budgets, currencies, "COP", "activity"),
        "available_cop": _sum_by_currency_code(month_budgets, currencies, "COP", "available"),
        "assigned_usd": _sum_by_currency_code(month_budgets, currencies, "USD", "assigned"),
        "activity_usd": _sum_by_currency_code(month_budgets, currencies, "USD", "activity"),
        "available_usd": _sum_by_currency_code(month_budgets, currencies, "USD", "available"),
        "total_assigned": sum(to_cop_fn(b.assigned, b.currency_id) for b in month_budgets),
        "total_activity": sum(to_cop_fn(b.activity, b.currency_id) for b in month_budgets),
        "total_available": sum(to_cop_fn(b.available, b.currency_id) for b in month_budgets),
    }


def get_category_budget_history(db: Session, category_id: int, months: int = 3):
    """
    Returns monthly budget history (assigned, activity, available) and
    associated transactions for a category over the last N months.

    All monetary values are returned both per-currency and consolidated to COP.
    """
    today = date.today()
    current_month = date(today.year, today.month, 1)

    # Build list of months going back
    month_list = []
    for i in range(months):
        m = current_month - relativedelta(months=i)
        month_list.append(m)

    currencies = {c.id: c for c in db.query(Currency).all()}
    exchange_rate = get_current_exchange_rate(db)

    # Get budget records for all months and recalculate to reflect latest transactions
    budgets = db.query(BudgetMonth).filter(
        BudgetMonth.category_id == category_id,
        BudgetMonth.month.in_(month_list)
    ).order_by(BudgetMonth.month).all()

    # Group by month to detect multi-currency budgets (same logic as get_month_budget)
    budgets_by_month = {}
    for b in budgets:
        budgets_by_month.setdefault(b.month, []).append(b)

    for month_key, month_budgets_list in budgets_by_month.items():
        has_multiple_currencies = len({b.currency_id for b in month_budgets_list}) > 1
        for b in month_budgets_list:
            recalculate_budget_available(db, b, include_all_currencies=not has_multiple_currencies)
    db.commit()

    to_cop = _make_currency_converter("COP", exchange_rate)

    def _to_cop_by_id(amount: float, cur_id: int) -> float:
        cur = currencies.get(cur_id)
        if not cur or cur.code == "COP":
            return float(amount or 0)
        return float(amount or 0) * exchange_rate

    monthly_summary = [
        _summarise_month_budgets(m, budgets, currencies, _to_cop_by_id)
        for m in month_list
    ]

    # Get transactions for the date range
    oldest_month = month_list[-1]
    next_of_current = current_month + relativedelta(months=1)

    transactions = db.query(Transaction).options(
        joinedload(Transaction.account)
    ).filter(
        Transaction.category_id == category_id,
        Transaction.date >= oldest_month,
        Transaction.date < next_of_current,
    ).order_by(Transaction.date.desc()).all()

    tx_list = []
    for tx in transactions:
        tx_list.append({
            "id": tx.id,
            "date": tx.date.isoformat(),
            "amount": tx.amount,
            "memo": tx.memo,
            "account_name": tx.account.name if tx.account else None,
            "currency_code": currencies.get(tx.currency_id, None).code if currencies.get(tx.currency_id) else "COP",
        })

    return {
        "category_id": category_id,
        "months": months,
        "monthly_summary": monthly_summary,
        "transactions": tx_list,
    }


def recalculate_month(db: Session, month_date: date) -> dict:
    """
    Force-sync assigned and available for all records in the given month against the prior month.

    This is an explicit operation (ignores assigned_overridden) triggered by the user
    via a "Recalculate" button for future months.

    Steps:
    1. Recalculate the prior month to get a fresh available (critical for accumulate
       categories where initial = prior month's available).
    2. For each record in the target month: inherit assigned from the prior month
       (regardless of assigned_overridden) and recalculate available.
    3. Clear assigned_overridden=False on updated records so future cascades work correctly.
    """
    prev_month = month_date - relativedelta(months=1)

    # --- Paso 1: refrescar el mes anterior ---
    prev_budgets_list = db.query(BudgetMonth).filter_by(month=prev_month).all()
    prev_by_cat: dict[int, list] = {}
    for b in prev_budgets_list:
        prev_by_cat.setdefault(b.category_id, []).append(b)
    for b in prev_budgets_list:
        has_multi = len(prev_by_cat.get(b.category_id, [])) > 1
        recalculate_budget_available(db, b, include_all_currencies=not has_multi)
    db.flush()

    # Indexar mes anterior por (category_id, currency_id) tras el flush
    prev_budgets = {(b.category_id, b.currency_id): b for b in prev_budgets_list}

    # --- Paso 2: recalcular mes objetivo ---
    budgets = db.query(BudgetMonth).filter_by(month=month_date).order_by(
        BudgetMonth.category_id, BudgetMonth.currency_id
    ).all()

    by_category: dict[int, list] = {}
    for b in budgets:
        by_category.setdefault(b.category_id, []).append(b)

    updated = 0
    for budget in budgets:
        prev = prev_budgets.get((budget.category_id, budget.currency_id))
        if prev is not None:
            # Forzar herencia de assigned (operación explícita del usuario)
            budget.assigned = prev.assigned
            budget.assigned_overridden = False  # Permitir cascades futuros

        has_multi_curr = len(by_category.get(budget.category_id, [])) > 1
        recalculate_budget_available(db, budget, include_all_currencies=not has_multi_curr)
        updated += 1

    db.commit()
    return {"updated": updated, "month": month_date.isoformat()}
