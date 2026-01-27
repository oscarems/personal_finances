"""
Reports and Analytics API
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_
from typing import Optional, Tuple
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from backend.database import get_db
from backend.models import Transaction, Category, CategoryGroup, Account, Currency, ExchangeRate, BudgetMonth, Debt, DebtPayment, WealthAsset
from backend.utils.wealth import apply_expected_appreciation

router = APIRouter()


def get_exchange_rate(db: Session) -> float:
    """Get current USD to COP exchange rate"""
    rate = db.query(ExchangeRate).order_by(ExchangeRate.date.desc()).first()
    return rate.rate if rate else 4000.0  # Default fallback


def parse_date_range(start_date: Optional[str], end_date: Optional[str]) -> Tuple[date, date]:
    """Parse ISO date strings, defaulting to current month."""
    today = date.today()
    if not start_date:
        start_date = today.replace(day=1).isoformat()
    if not end_date:
        end_date = today.isoformat()

    return date.fromisoformat(start_date), date.fromisoformat(end_date)


def convert_to_currency(amount: float, from_currency_id: int, to_currency_id: int, exchange_rate: float) -> float:
    """Convert amount from one currency to another

    Args:
        amount: Amount to convert
        from_currency_id: Source currency ID (1=COP, 2=USD)
        to_currency_id: Target currency ID (1=COP, 2=USD)
        exchange_rate: USD to COP exchange rate

    Returns:
        Converted amount
    """
    if from_currency_id == to_currency_id:
        return amount

    # Convert USD to COP
    if from_currency_id == 2 and to_currency_id == 1:
        return amount * exchange_rate

    # Convert COP to USD
    if from_currency_id == 1 and to_currency_id == 2:
        return amount / exchange_rate

    return amount


@router.get("/spending-by-category")
def get_spending_by_category(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Get spending grouped by category for a date range
    Now includes ALL currencies, converted to the selected one
    """
    # Default to current month if no dates provided
    if not start_date:
        start_date = date.today().replace(day=1).isoformat()
    if not end_date:
        end_date = date.today().isoformat()

    # Get exchange rate for conversion
    exchange_rate = get_exchange_rate(db)

    # Query ALL transactions (not filtered by currency)
    query = db.query(
        Category.name.label('category_name'),
        CategoryGroup.name.label('group_name'),
        Transaction.amount,
        Transaction.currency_id
    ).join(
        Category, Transaction.category_id == Category.id
    ).join(
        CategoryGroup, Category.category_group_id == CategoryGroup.id
    ).filter(
        and_(
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.amount < 0  # Only expenses (negative amounts)
        )
    ).all()

    # Group by category and convert amounts
    category_totals = {}
    for row in query:
        key = (row.category_name, row.group_name)
        converted_amount = convert_to_currency(
            abs(row.amount),
            row.currency_id,
            currency_id,
            exchange_rate
        )

        if key not in category_totals:
            category_totals[key] = 0
        category_totals[key] += converted_amount

    # Format results
    results = []
    for (category_name, group_name), total in category_totals.items():
        results.append({
            'category': category_name,
            'group': group_name,
            'amount': total
        })

    # Sort by amount descending (highest expenses first)
    results.sort(key=lambda x: x['amount'], reverse=True)

    # Calculate total
    total_expenses = sum(r['amount'] for r in results)

    return {
        'start_date': start_date,
        'end_date': end_date,
        'total_expenses': total_expenses,
        'categories': results
    }


@router.get("/spending-by-group")
def get_spending_by_group(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Get spending grouped by category group
    Now includes ALL currencies, converted to the selected one
    """
    # Default to current month if no dates provided
    if not start_date:
        start_date = date.today().replace(day=1).isoformat()
    if not end_date:
        end_date = date.today().isoformat()

    # Get exchange rate for conversion
    exchange_rate = get_exchange_rate(db)

    # Query ALL transactions (not filtered by currency)
    query = db.query(
        CategoryGroup.name.label('group_name'),
        Transaction.amount,
        Transaction.currency_id
    ).join(
        Category, Transaction.category_id == Category.id
    ).join(
        CategoryGroup, Category.category_group_id == CategoryGroup.id
    ).filter(
        and_(
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.amount < 0  # Only expenses
        )
    ).all()

    # Group by group and convert amounts
    group_totals = {}
    for row in query:
        group_name = row.group_name
        converted_amount = convert_to_currency(
            abs(row.amount),
            row.currency_id,
            currency_id,
            exchange_rate
        )

        if group_name not in group_totals:
            group_totals[group_name] = 0
        group_totals[group_name] += converted_amount

    # Format results
    results = []
    for group_name, total in group_totals.items():
        results.append({
            'group': group_name,
            'amount': total
        })

    # Sort by amount descending
    results.sort(key=lambda x: x['amount'], reverse=True)

    total_expenses = sum(r['amount'] for r in results)

    return {
        'start_date': start_date,
        'end_date': end_date,
        'total_expenses': total_expenses,
        'groups': results
    }


@router.get("/income-vs-expenses")
def get_income_vs_expenses(
    months: int = 6,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Get income vs expenses for the last N months
    Now includes ALL currencies, converted to the selected one
    """
    # Calculate start date (N months ago)
    end_date = date.today()
    start_date = end_date - relativedelta(months=months)
    min_start_date = date(2026, 1, 1)
    note = None
    if start_date < min_start_date:
        start_date = min_start_date
        note = 'Los datos anteriores a enero de 2026 no se pueden mostrar porque no se tiene registro.'

    # Get exchange rate for conversion
    exchange_rate = get_exchange_rate(db)

    # Query for monthly totals
    results = []
    current_date = start_date.replace(day=1)

    while current_date <= end_date:
        month_start = current_date
        month_end = current_date + relativedelta(months=1) - relativedelta(days=1)

        # Income (positive amounts) - ALL currencies
        income_transactions = db.query(
            Transaction.amount,
            Transaction.currency_id
        ).filter(
            and_(
                Transaction.date >= month_start,
                Transaction.date <= month_end,
                Transaction.amount > 0,
                Transaction.transfer_account_id.is_(None)
            )
        ).all()

        income = sum(
            convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
            for t in income_transactions
        )

        # Expenses (negative amounts) - ALL currencies
        expense_transactions = db.query(
            Transaction.amount,
            Transaction.currency_id
        ).filter(
            and_(
                Transaction.date >= month_start,
                Transaction.date <= month_end,
                Transaction.amount < 0,
                Transaction.transfer_account_id.is_(None)
            )
        ).all()

        expenses = sum(
            convert_to_currency(abs(t.amount), t.currency_id, currency_id, exchange_rate)
            for t in expense_transactions
        )

        results.append({
            'month': current_date.strftime('%Y-%m'),
            'month_name': current_date.strftime('%b %Y'),
            'income': income,
            'expenses': expenses,
            'net': income - expenses
        })

        current_date += relativedelta(months=1)

    return {
        'months': results,
        'period': f'{start_date.strftime("%b %Y")} - {end_date.strftime("%b %Y")}',
        'note': note
    }


@router.get("/budget-income-expenses")
def get_budget_income_expenses(
    months: int = 12,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Get budget vs income vs expenses over time
    Now includes ALL currencies, converted to the selected one
    """
    end_date = date.today()
    start_date = end_date - relativedelta(months=months)
    min_start_date = date(2026, 1, 1)
    note = None
    if start_date < min_start_date:
        start_date = min_start_date
        note = 'Los datos anteriores a enero de 2026 no se pueden mostrar porque no se tiene registro.'

    exchange_rate = get_exchange_rate(db)

    budget_totals = {}
    budget_data = db.query(BudgetMonth).filter(
        and_(
            BudgetMonth.month >= start_date.replace(day=1),
            BudgetMonth.month <= end_date
        )
    ).all()

    for budget_month in budget_data:
        month_key = budget_month.month.strftime('%Y-%m')
        budgeted_converted = convert_to_currency(
            budget_month.assigned or 0,
            budget_month.currency_id,
            currency_id,
            exchange_rate
        )
        budget_totals[month_key] = budget_totals.get(month_key, 0) + budgeted_converted

    results = []
    current_date = start_date.replace(day=1)

    while current_date <= end_date:
        month_start = current_date
        month_end = current_date + relativedelta(months=1) - relativedelta(days=1)

        income_transactions = db.query(
            Transaction.amount,
            Transaction.currency_id
        ).filter(
            and_(
                Transaction.date >= month_start,
                Transaction.date <= month_end,
                Transaction.amount > 0,
                Transaction.transfer_account_id.is_(None)
            )
        ).all()

        income = sum(
            convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
            for t in income_transactions
        )

        expense_transactions = db.query(
            Transaction.amount,
            Transaction.currency_id
        ).filter(
            and_(
                Transaction.date >= month_start,
                Transaction.date <= month_end,
                Transaction.amount < 0,
                Transaction.transfer_account_id.is_(None)
            )
        ).all()

        expenses = sum(
            convert_to_currency(abs(t.amount), t.currency_id, currency_id, exchange_rate)
            for t in expense_transactions
        )

        month_key = current_date.strftime('%Y-%m')
        budget = budget_totals.get(month_key, 0)

        results.append({
            'month': month_key,
            'month_name': current_date.strftime('%b %Y'),
            'budget': budget,
            'income': income,
            'expenses': expenses
        })

        current_date += relativedelta(months=1)

    currency = db.query(Currency).get(currency_id)

    return {
        'months': results,
        'period': f'{start_date.strftime("%b %Y")} - {end_date.strftime("%b %Y")}',
        'note': note,
        'currency': currency.to_dict() if currency else None
    }


@router.get("/debt-balance-history")
def get_debt_balance_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Get total debt balance over time using debt payments history.
    """
    debts = db.query(Debt).filter(Debt.is_active == True).all()
    if not debts:
        return {
            'monthly': [],
            'currency': None,
            'current_total_debt': 0
        }

    today = date.today()
    if not end_date:
        end_date_obj = today
    else:
        end_date_obj = date.fromisoformat(end_date)

    if not start_date:
        earliest_dates = []
        for debt in debts:
            if debt.start_date:
                earliest_dates.append(debt.start_date)
            if debt.payments:
                earliest_dates.append(min(p.payment_date for p in debt.payments if p.payment_date))
        start_date_obj = min(earliest_dates) if earliest_dates else today
    else:
        start_date_obj = date.fromisoformat(start_date)

    start_date_obj = start_date_obj.replace(day=1)
    end_date_obj = end_date_obj.replace(day=1)

    exchange_rate = get_exchange_rate(db)
    currencies = db.query(Currency).all()
    currency_map = {currency.code: currency.id for currency in currencies}

    monthly_totals = []
    current_date = start_date_obj

    while current_date <= end_date_obj:
        month_end = current_date + relativedelta(months=1) - relativedelta(days=1)
        total_debt = 0.0

        for debt in debts:
            if debt.start_date and debt.start_date > month_end:
                continue

            payments = sorted(
                [p for p in debt.payments if p.payment_date and p.payment_date <= month_end],
                key=lambda p: p.payment_date
            )

            if payments:
                last_payment = payments[-1]
                if last_payment.balance_after is not None:
                    balance = last_payment.balance_after
                else:
                    balance = debt.original_amount
                    for payment in payments:
                        payment_amount = payment.principal if payment.principal is not None else payment.amount
                        balance -= payment_amount
            else:
                balance = debt.original_amount

            if month_end >= today and debt.current_balance is not None:
                balance = debt.current_balance

            balance = max(balance, 0)
            debt_currency_id = currency_map.get(debt.currency_code, currency_id)
            total_debt += convert_to_currency(
                balance,
                debt_currency_id,
                currency_id,
                exchange_rate
            )

        monthly_totals.append({
            'month': current_date.strftime('%Y-%m'),
            'month_name': current_date.strftime('%b %Y'),
            'total_debt': round(total_debt, 2)
        })

        current_date += relativedelta(months=1)

    currency = db.query(Currency).get(currency_id)

    return {
        'monthly': monthly_totals,
        'current_total_debt': monthly_totals[-1]['total_debt'] if monthly_totals else 0,
        'currency': currency.to_dict() if currency else None
    }


@router.get("/spending-trends")
def get_spending_trends(
    category_id: Optional[int] = None,
    months: int = 12,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Get spending trends over time for a specific category or all categories
    Now includes ALL currencies, converted to the selected one
    """
    end_date = date.today()
    start_date = end_date - relativedelta(months=months)

    # Get exchange rate for conversion
    exchange_rate = get_exchange_rate(db)

    results = []
    current_date = start_date.replace(day=1)

    while current_date <= end_date:
        month_start = current_date
        month_end = current_date + relativedelta(months=1) - relativedelta(days=1)

        # Build query for ALL currencies
        query = db.query(
            Transaction.amount,
            Transaction.currency_id
        ).filter(
            and_(
                Transaction.date >= month_start,
                Transaction.date <= month_end,
                Transaction.amount < 0  # Only expenses
            )
        )

        if category_id:
            query = query.filter(Transaction.category_id == category_id)

        transactions = query.all()
        total = sum(
            convert_to_currency(abs(t.amount), t.currency_id, currency_id, exchange_rate)
            for t in transactions
        )

        results.append({
            'month': current_date.strftime('%Y-%m'),
            'month_name': current_date.strftime('%b %Y'),
            'amount': total
        })

        current_date += relativedelta(months=1)

    # Get category name if specified
    category_name = None
    if category_id:
        category = db.query(Category).get(category_id)
        if category:
            category_name = category.name

    return {
        'category': category_name or 'Todos los gastos',
        'months': results,
        'period': f'{start_date.strftime("%b %Y")} - {end_date.strftime("%b %Y")}'
    }


@router.get("/summary")
def get_summary(
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Get overall financial summary
    Now includes ALL currencies, converted to the selected one
    """
    today = date.today()
    month_start = today.replace(day=1)

    # Get exchange rate for conversion
    exchange_rate = get_exchange_rate(db)

    # Current month income - ALL currencies
    income_transactions = db.query(
        Transaction.amount,
        Transaction.currency_id
    ).filter(
        and_(
            Transaction.date >= month_start,
            Transaction.date <= today,
            Transaction.amount > 0,
            Transaction.transfer_account_id.is_(None)
        )
    ).all()

    month_income = sum(
        convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
        for t in income_transactions
    )

    # Current month expenses - ALL currencies
    expense_transactions = db.query(
        Transaction.amount,
        Transaction.currency_id
    ).filter(
        and_(
            Transaction.date >= month_start,
            Transaction.date <= today,
            Transaction.amount < 0,
            Transaction.transfer_account_id.is_(None)
        )
    ).all()

    month_expenses = sum(
        convert_to_currency(abs(t.amount), t.currency_id, currency_id, exchange_rate)
        for t in expense_transactions
    )

    # Account balances - ALL currencies
    accounts = db.query(Account).filter(
        Account.is_closed == False
    ).all()

    total_balance = sum(
        convert_to_currency(acc.balance, acc.currency_id, currency_id, exchange_rate)
        for acc in accounts
    )

    # Get currency
    currency = db.query(Currency).get(currency_id)

    return {
        'current_month': {
            'income': month_income,
            'expenses': month_expenses,
            'net': month_income - month_expenses
        },
        'accounts': {
            'total_balance': total_balance,
            'count': len(accounts)
        },
        'currency': currency.to_dict() if currency else None
    }


@router.get("/period-summary")
def get_period_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Get income, expenses, and average monthly expenses for a period
    Transfers between accounts are excluded.
    """
    start_date_obj, end_date_obj = parse_date_range(start_date, end_date)
    exchange_rate = get_exchange_rate(db)

    income_transactions = db.query(
        Transaction.amount,
        Transaction.currency_id
    ).filter(
        and_(
            Transaction.date >= start_date_obj,
            Transaction.date <= end_date_obj,
            Transaction.amount > 0,
            Transaction.transfer_account_id.is_(None)
        )
    ).all()

    expense_transactions = db.query(
        Transaction.amount,
        Transaction.currency_id
    ).filter(
        and_(
            Transaction.date >= start_date_obj,
            Transaction.date <= end_date_obj,
            Transaction.amount < 0,
            Transaction.transfer_account_id.is_(None)
        )
    ).all()

    total_income = sum(
        convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
        for t in income_transactions
    )

    total_expenses = sum(
        convert_to_currency(abs(t.amount), t.currency_id, currency_id, exchange_rate)
        for t in expense_transactions
    )

    months_count = (end_date_obj.year - start_date_obj.year) * 12 + (end_date_obj.month - start_date_obj.month) + 1
    average_monthly_expenses = total_expenses / months_count if months_count > 0 else 0

    currency = db.query(Currency).get(currency_id)

    return {
        'start_date': start_date_obj.isoformat(),
        'end_date': end_date_obj.isoformat(),
        'total_income': total_income,
        'total_expenses': total_expenses,
        'average_monthly_expenses': average_monthly_expenses,
        'currency': currency.to_dict() if currency else None
    }


@router.get("/balance-trend")
def get_balance_trend(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Get total account balance trend over time for active accounts.
    """
    start_date_obj, end_date_obj = parse_date_range(start_date, end_date)
    exchange_rate = get_exchange_rate(db)

    accounts = db.query(Account).filter(Account.is_closed == False).all()
    account_ids = [account.id for account in accounts]

    current_total_balance = sum(
        convert_to_currency(account.balance, account.currency_id, currency_id, exchange_rate)
        for account in accounts
    )

    if not account_ids:
        return {'months': []}

    transactions_after_start = db.query(
        Transaction.amount,
        Transaction.currency_id,
        Transaction.date
    ).filter(
        and_(
            Transaction.account_id.in_(account_ids),
            Transaction.date >= start_date_obj
        )
    ).all()

    net_after_start = sum(
        convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
        for t in transactions_after_start
    )

    start_balance = current_total_balance - net_after_start

    initial_balance_adjustments = {}
    for account in accounts:
        if not account.created_at:
            continue
        created_date = account.created_at.date()
        if created_date <= start_date_obj or created_date > end_date_obj:
            continue

        transactions_after_creation = db.query(
            Transaction.amount,
            Transaction.currency_id
        ).filter(
            and_(
                Transaction.account_id == account.id,
                Transaction.date >= created_date
            )
        ).all()

        net_after_creation = sum(
            convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
            for t in transactions_after_creation
        )

        initial_balance = convert_to_currency(
            account.balance,
            account.currency_id,
            currency_id,
            exchange_rate
        ) - net_after_creation

        start_balance -= initial_balance

        month_key = created_date.strftime('%Y-%m')
        initial_balance_adjustments[month_key] = (
            initial_balance_adjustments.get(month_key, 0.0) + initial_balance
        )

    transactions_in_range = db.query(
        Transaction.amount,
        Transaction.currency_id,
        Transaction.date
    ).filter(
        and_(
            Transaction.account_id.in_(account_ids),
            Transaction.date >= start_date_obj,
            Transaction.date <= end_date_obj
        )
    ).all()

    monthly_net = {}
    for transaction in transactions_in_range:
        month_key = transaction.date.strftime('%Y-%m')
        monthly_net.setdefault(month_key, 0.0)
        monthly_net[month_key] += convert_to_currency(
            transaction.amount,
            transaction.currency_id,
            currency_id,
            exchange_rate
        )

    for month_key, adjustment in initial_balance_adjustments.items():
        monthly_net.setdefault(month_key, 0.0)
        monthly_net[month_key] += adjustment

    months = []
    running_balance = start_balance
    current_date = start_date_obj.replace(day=1)
    previous_balance = None

    while current_date <= end_date_obj:
        month_key = current_date.strftime('%Y-%m')
        running_balance += monthly_net.get(month_key, 0.0)
        change = running_balance - previous_balance if previous_balance is not None else None
        months.append({
            'month': month_key,
            'month_name': current_date.strftime('%b %Y'),
            'balance': running_balance,
            'change': change
        })
        previous_balance = running_balance
        current_date += relativedelta(months=1)

    latest_change = None
    latest_change_month = None
    if len(months) > 1:
        latest_change = months[-1]['change']
        latest_change_month = months[-1]['month_name']

    return {
        'start_date': start_date_obj.isoformat(),
        'end_date': end_date_obj.isoformat(),
        'months': months,
        'latest_change': latest_change,
        'latest_change_month': latest_change_month
    }


@router.get("/account-balance-history")
def get_account_balance_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currency_id: int = 1,
    interval: str = Query("monthly"),
    db: Session = Depends(get_db)
):
    """
    Get total account balances over time for active accounts.
    Interval can be daily or monthly.
    """
    if interval not in {"daily", "monthly"}:
        raise HTTPException(status_code=400, detail="Invalid interval. Use daily or monthly.")

    start_date_obj, end_date_obj = parse_date_range(start_date, end_date)
    exchange_rate = get_exchange_rate(db)

    accounts = db.query(Account).filter(Account.is_closed == False).all()
    account_ids = [account.id for account in accounts]

    if not account_ids:
        return {'points': []}

    current_total_balance = sum(
        convert_to_currency(account.balance, account.currency_id, currency_id, exchange_rate)
        for account in accounts
    )

    transactions_after_start = db.query(
        Transaction.amount,
        Transaction.currency_id,
        Transaction.date
    ).filter(
        and_(
            Transaction.account_id.in_(account_ids),
            Transaction.date >= start_date_obj
        )
    ).all()

    net_after_start = sum(
        convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
        for t in transactions_after_start
    )

    start_balance = current_total_balance - net_after_start

    initial_balance_adjustments = {}
    for account in accounts:
        if not account.created_at:
            continue
        created_date = account.created_at.date()
        if created_date <= start_date_obj or created_date > end_date_obj:
            continue

        transactions_after_creation = db.query(
            Transaction.amount,
            Transaction.currency_id
        ).filter(
            and_(
                Transaction.account_id == account.id,
                Transaction.date >= created_date
            )
        ).all()

        net_after_creation = sum(
            convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
            for t in transactions_after_creation
        )

        initial_balance = convert_to_currency(
            account.balance,
            account.currency_id,
            currency_id,
            exchange_rate
        ) - net_after_creation

        start_balance -= initial_balance

        if interval == "daily":
            key = created_date.strftime('%Y-%m-%d')
        else:
            key = created_date.strftime('%Y-%m')
        initial_balance_adjustments[key] = (
            initial_balance_adjustments.get(key, 0.0) + initial_balance
        )

    transactions_in_range = db.query(
        Transaction.amount,
        Transaction.currency_id,
        Transaction.date
    ).filter(
        and_(
            Transaction.account_id.in_(account_ids),
            Transaction.date >= start_date_obj,
            Transaction.date <= end_date_obj
        )
    ).all()

    period_net = {}
    for transaction in transactions_in_range:
        if interval == "daily":
            period_key = transaction.date.strftime('%Y-%m-%d')
        else:
            period_key = transaction.date.strftime('%Y-%m')
        period_net.setdefault(period_key, 0.0)
        period_net[period_key] += convert_to_currency(
            transaction.amount,
            transaction.currency_id,
            currency_id,
            exchange_rate
        )

    for period_key, adjustment in initial_balance_adjustments.items():
        period_net.setdefault(period_key, 0.0)
        period_net[period_key] += adjustment

    points = []
    running_balance = start_balance

    if interval == "daily":
        current_date = start_date_obj
        while current_date <= end_date_obj:
            period_key = current_date.strftime('%Y-%m-%d')
            running_balance += period_net.get(period_key, 0.0)
            points.append({
                'date': period_key,
                'label': current_date.strftime('%d %b %Y'),
                'balance': running_balance
            })
            current_date += relativedelta(days=1)
    else:
        current_date = start_date_obj.replace(day=1)
        while current_date <= end_date_obj:
            period_key = current_date.strftime('%Y-%m')
            running_balance += period_net.get(period_key, 0.0)
            points.append({
                'date': period_key,
                'label': current_date.strftime('%b %Y'),
                'balance': running_balance
            })
            current_date += relativedelta(months=1)

    return {
        'start_date': start_date_obj.isoformat(),
        'end_date': end_date_obj.isoformat(),
        'interval': interval,
        'points': points
    }


@router.get("/savings-rate")
def get_savings_rate(
    months: int = 12,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Calculate savings rate (Income - Expenses) / Income * 100
    Returns monthly, quarterly, and yearly averages
    Excludes transfers
    """
    end_date = date.today()
    start_date = end_date - relativedelta(months=months)
    min_start_date = date(2026, 1, 1)
    if start_date < min_start_date:
        start_date = min_start_date

    exchange_rate = get_exchange_rate(db)

    # Get monthly data
    monthly_data = []
    current_date = start_date.replace(day=1)

    while current_date <= end_date:
        month_start = current_date
        month_end = current_date + relativedelta(months=1) - relativedelta(days=1)

        # Income (excludes transfers)
        income_transactions = db.query(
            Transaction.amount,
            Transaction.currency_id
        ).filter(
            and_(
                Transaction.date >= month_start,
                Transaction.date <= month_end,
                Transaction.amount > 0,
                Transaction.transfer_account_id.is_(None)
            )
        ).all()

        income = sum(
            convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
            for t in income_transactions
        )

        # Expenses (excludes transfers)
        expense_transactions = db.query(
            Transaction.amount,
            Transaction.currency_id
        ).filter(
            and_(
                Transaction.date >= month_start,
                Transaction.date <= month_end,
                Transaction.amount < 0,
                Transaction.transfer_account_id.is_(None)
            )
        ).all()

        expenses = sum(
            convert_to_currency(abs(t.amount), t.currency_id, currency_id, exchange_rate)
            for t in expense_transactions
        )

        # Calculate savings and rate
        savings = income - expenses
        savings_rate = (savings / income * 100) if income > 0 else 0

        monthly_data.append({
            'month': current_date.strftime('%Y-%m'),
            'month_name': current_date.strftime('%b %Y'),
            'income': income,
            'expenses': expenses,
            'savings': savings,
            'savings_rate': round(savings_rate, 2)
        })

        current_date += relativedelta(months=1)

    # Calculate overall average
    total_income = sum(m['income'] for m in monthly_data)
    total_expenses = sum(m['expenses'] for m in monthly_data)
    total_savings = total_income - total_expenses
    avg_savings_rate = (total_savings / total_income * 100) if total_income > 0 else 0

    currency = db.query(Currency).get(currency_id)

    return {
        'monthly': monthly_data,
        'average_savings_rate': round(avg_savings_rate, 2),
        'total_income': total_income,
        'total_expenses': total_expenses,
        'total_savings': total_savings,
        'period': f'{start_date.strftime("%b %Y")} - {end_date.strftime("%b %Y")}',
        'currency': currency.to_dict() if currency else None
    }


@router.get("/budget-vs-actual")
def get_budget_vs_actual(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Compare budgeted amounts vs actual spending by category
    Defaults to January 2026 onwards if no dates provided
    """
    # Always use previous month regardless of input
    today = date.today()
    start_date_obj = today.replace(day=1) - relativedelta(months=1)
    end_date_obj = today.replace(day=1) - relativedelta(days=1)

    exchange_rate = get_exchange_rate(db)

    # Get all budget months in range
    budget_data = db.query(BudgetMonth).filter(
        and_(
            BudgetMonth.month >= start_date_obj,
            BudgetMonth.month <= end_date_obj
        )
    ).all()

    # Group by category
    category_summary = {}

    for budget_month in budget_data:
        category_id = budget_month.category_id

        if category_id not in category_summary:
            category = db.query(Category).get(category_id)
            category_summary[category_id] = {
                'category_id': category_id,
                'category_name': category.name if category else 'Unknown',
                'category_group': category.category_group.name if category and category.category_group else 'Unknown',
                'budgeted': 0,
                'actual': 0,
                'difference': 0,
                'percentage': 0
            }

        # Convert budgeted amount to selected currency
        budgeted_converted = convert_to_currency(
            budget_month.assigned or 0,
            budget_month.currency_id,
            currency_id,
            exchange_rate
        )

        category_summary[category_id]['budgeted'] += budgeted_converted

        # Get actual spending for this category in this month
        month_start = budget_month.month
        month_end = month_start + relativedelta(months=1) - relativedelta(days=1)

        actual_transactions = db.query(
            Transaction.amount,
            Transaction.currency_id
        ).filter(
            and_(
                Transaction.category_id == category_id,
                Transaction.date >= month_start,
                Transaction.date <= month_end,
                Transaction.amount < 0  # Only expenses
            )
        ).all()

        actual_spent = sum(
            convert_to_currency(abs(t.amount), t.currency_id, currency_id, exchange_rate)
            for t in actual_transactions
        )

        category_summary[category_id]['actual'] += actual_spent

    # Calculate differences and percentages
    results = []
    for cat_id, data in category_summary.items():
        difference = data['budgeted'] - data['actual']
        percentage = (data['actual'] / data['budgeted'] * 100) if data['budgeted'] > 0 else 0

        data['difference'] = difference
        data['percentage'] = round(percentage, 2)
        data['status'] = 'under' if difference > 0 else ('over' if difference < 0 else 'exact')

        results.append(data)

    # Sort by overspending (most overspent first)
    results.sort(key=lambda x: x['difference'])

    # Calculate totals
    total_budgeted = sum(r['budgeted'] for r in results)
    total_actual = sum(r['actual'] for r in results)
    total_difference = total_budgeted - total_actual

    currency = db.query(Currency).get(currency_id)

    return {
        'start_date': start_date_obj.isoformat(),
        'end_date': end_date_obj.isoformat(),
        'month_label': start_date_obj.strftime('%b %Y'),
        'categories': results,
        'totals': {
            'budgeted': total_budgeted,
            'actual': total_actual,
            'difference': total_difference,
            'percentage': round((total_actual / total_budgeted * 100) if total_budgeted > 0 else 0, 2)
        },
        'currency': currency.to_dict() if currency else None
    }


@router.get("/net-worth")
def get_net_worth(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Calculate net worth (Assets - Liabilities) over time
    Defaults to January 2026 onwards if no dates provided
    Assets: checking, savings, cash, CDT, investment accounts (positive balances)
    Liabilities: credit cards, loans, mortgages (negative balances or debt accounts)
    """
    # Default to January 2026 if not specified
    if not start_date:
        start_date = '2026-01-01'
    if not end_date:
        end_date = date.today().isoformat()

    start_date_obj = date.fromisoformat(start_date)
    end_date_obj = date.fromisoformat(end_date)

    exchange_rate = get_exchange_rate(db)

    # Get all accounts
    accounts = db.query(Account).filter(Account.is_closed == False).all()
    wealth_assets = db.query(WealthAsset).all()

    # Asset account types
    asset_types = ['checking', 'savings', 'cash', 'cdt', 'investment']
    # Liability account types
    liability_types = ['credit_card', 'credit_loan', 'mortgage']

    monthly_net_worth = []
    current_date = start_date_obj.replace(day=1)

    while current_date <= end_date_obj:
        month_start = current_date
        month_end = current_date + relativedelta(months=1) - relativedelta(days=1)

        assets = 0
        liabilities = 0

        for account in accounts:
            # Skip accounts created after this month
            if account.created_at and account.created_at.date() > month_end:
                continue

            # Calculate account balance at end of this month
            # Start with current balance
            current_balance = account.balance

            # Subtract all transactions after month_end
            future_transactions = db.query(
                Transaction.amount,
                Transaction.currency_id
            ).filter(
                and_(
                    Transaction.account_id == account.id,
                    Transaction.date > month_end
                )
            ).all()

            balance_at_month_end = convert_to_currency(
                current_balance,
                account.currency_id,
                currency_id,
                exchange_rate
            )

            for txn in future_transactions:
                balance_at_month_end -= convert_to_currency(
                    txn.amount,
                    txn.currency_id,
                    currency_id,
                    exchange_rate
                )

            # Categorize as asset or liability
            if account.type in asset_types:
                assets += balance_at_month_end
            elif account.type in liability_types:
                # For credit cards/loans, negative balance = owe money
                # So we add absolute value to liabilities
                liabilities += abs(balance_at_month_end)

        additional_assets = 0
        for asset in wealth_assets:
            if asset.as_of_date and asset.as_of_date > month_end:
                continue
            effective_value = apply_expected_appreciation(
                asset.value,
                asset.expected_appreciation_rate if asset.asset_class == "inmueble" else None,
                asset.as_of_date,
                month_end
            )
            additional_assets += convert_to_currency(
                effective_value,
                asset.currency_id,
                currency_id,
                exchange_rate
            )

        assets += additional_assets

        net_worth = assets - liabilities

        monthly_net_worth.append({
            'month': current_date.strftime('%Y-%m'),
            'month_name': current_date.strftime('%b %Y'),
            'assets': round(assets, 2),
            'liabilities': round(liabilities, 2),
            'net_worth': round(net_worth, 2)
        })

        current_date += relativedelta(months=1)

    # Calculate change over period
    if len(monthly_net_worth) > 1:
        first_net_worth = monthly_net_worth[0]['net_worth']
        last_net_worth = monthly_net_worth[-1]['net_worth']
        change = last_net_worth - first_net_worth
        change_percentage = (change / first_net_worth * 100) if first_net_worth != 0 else 0
    else:
        change = 0
        change_percentage = 0

    currency = db.query(Currency).get(currency_id)

    return {
        'start_date': start_date_obj.isoformat(),
        'end_date': end_date_obj.isoformat(),
        'monthly': monthly_net_worth,
        'change': round(change, 2),
        'change_percentage': round(change_percentage, 2),
        'current_net_worth': monthly_net_worth[-1]['net_worth'] if monthly_net_worth else 0,
        'currency': currency.to_dict() if currency else None
    }


@router.get("/debt-summary")
def get_debt_summary(
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Summary of all active debts with amortization info
    Shows current balances, monthly payments, interest rates, and payoff dates
    """
    exchange_rate = get_exchange_rate(db)

    # Get all active debts
    debts = db.query(Debt).filter(Debt.is_active == True).all()

    debt_details = []
    total_debt = 0
    total_monthly_payment = 0
    total_interest_paid = 0

    for debt in debts:
        # Convert amounts to selected currency
        current_balance = convert_to_currency(
            debt.current_balance or 0,
            debt.currency_code,
            currency_id,
            exchange_rate
        )

        monthly_payment = convert_to_currency(
            debt.monthly_payment or 0,
            debt.currency_code,
            currency_id,
            exchange_rate
        )

        # Calculate interest paid (from debt_payments table)
        debt_payments = db.query(DebtPayment).filter(
            DebtPayment.debt_id == debt.id
        ).all()

        interest_paid = sum(
            convert_to_currency(
                payment.interest or 0,
                debt.currency_code,
                currency_id,
                exchange_rate
            )
            for payment in debt_payments
        )

        # Calculate months remaining
        if monthly_payment > 0 and current_balance > 0:
            months_remaining = current_balance / monthly_payment
        else:
            months_remaining = 0

        # Estimate payoff date
        payoff_date = None
        if months_remaining > 0:
            payoff_date = (date.today() + relativedelta(months=int(months_remaining))).isoformat()

        debt_details.append({
            'id': debt.id,
            'name': debt.name,
            'type': debt.debt_type,
            'institution': debt.institution,
            'current_balance': round(current_balance, 2),
            'original_amount': convert_to_currency(
                debt.original_amount or 0,
                debt.currency_code,
                currency_id,
                exchange_rate
            ),
            'monthly_payment': round(monthly_payment, 2),
            'interest_rate': debt.interest_rate,
            'interest_paid': round(interest_paid, 2),
            'months_remaining': round(months_remaining, 1),
            'payoff_date': payoff_date,
            'start_date': debt.start_date.isoformat() if debt.start_date else None,
            'payment_day': debt.payment_day
        })

        total_debt += current_balance
        total_monthly_payment += monthly_payment
        total_interest_paid += interest_paid

    # Sort by balance descending
    debt_details.sort(key=lambda x: x['current_balance'], reverse=True)

    currency = db.query(Currency).get(currency_id)

    return {
        'debts': debt_details,
        'totals': {
            'total_debt': round(total_debt, 2),
            'total_monthly_payment': round(total_monthly_payment, 2),
            'total_interest_paid': round(total_interest_paid, 2),
            'debt_count': len(debt_details)
        },
        'currency': currency.to_dict() if currency else None
    }


@router.get("/debt-payoff-projection")
def get_debt_payoff_projection(
    debt_id: int,
    extra_payment: float = 0,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Project debt payoff schedule with optional extra payments
    Shows month-by-month breakdown of principal, interest, and remaining balance
    """
    debt = db.query(Debt).get(debt_id)
    if not debt:
        raise HTTPException(status_code=404, detail="Debt not found")

    exchange_rate = get_exchange_rate(db)

    # Convert to selected currency
    current_balance = convert_to_currency(
        debt.current_balance or 0,
        debt.currency_code,
        currency_id,
        exchange_rate
    )

    monthly_payment = convert_to_currency(
        debt.monthly_payment or 0,
        debt.currency_code,
        currency_id,
        exchange_rate
    ) + extra_payment

    interest_rate = debt.interest_rate or 0
    monthly_interest_rate = (interest_rate / 100) / 12

    # Calculate amortization schedule
    schedule = []
    balance = current_balance
    month = 1
    total_interest = 0
    total_principal = 0

    while balance > 0 and month <= 360:  # Max 30 years
        # Calculate interest for this month
        interest_payment = balance * monthly_interest_rate
        principal_payment = min(monthly_payment - interest_payment, balance)

        # Handle case where payment is less than interest
        if principal_payment <= 0:
            break

        balance -= principal_payment
        total_interest += interest_payment
        total_principal += principal_payment

        payment_date = date.today() + relativedelta(months=month)

        schedule.append({
            'month': month,
            'date': payment_date.isoformat(),
            'payment': round(monthly_payment, 2),
            'principal': round(principal_payment, 2),
            'interest': round(interest_payment, 2),
            'balance': round(max(balance, 0), 2)
        })

        month += 1

        if balance <= 0:
            break

    payoff_date = schedule[-1]['date'] if schedule else None
    months_to_payoff = len(schedule)

    currency = db.query(Currency).get(currency_id)

    return {
        'debt': {
            'id': debt.id,
            'name': debt.name,
            'type': debt.debt_type,
            'current_balance': round(current_balance, 2),
            'interest_rate': interest_rate
        },
        'projection': {
            'monthly_payment': round(monthly_payment, 2),
            'extra_payment': round(extra_payment, 2),
            'months_to_payoff': months_to_payoff,
            'payoff_date': payoff_date,
            'total_interest': round(total_interest, 2),
            'total_principal': round(total_principal, 2),
            'total_paid': round(total_interest + total_principal, 2)
        },
        'schedule': schedule,
        'currency': currency.to_dict() if currency else None
    }
