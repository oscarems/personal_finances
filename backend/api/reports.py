"""
Reports and Analytics API
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_
from typing import Optional, Tuple
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from backend.database import get_db
from backend.models import Transaction, Category, CategoryGroup, Account, Currency, ExchangeRate

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
        'period': f'{start_date.strftime("%b %Y")} - {end_date.strftime("%b %Y")}'
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
            Transaction.date > start_date_obj
        )
    ).all()

    net_after_start = sum(
        convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
        for t in transactions_after_start
    )

    start_balance = current_total_balance - net_after_start

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

    months = []
    running_balance = start_balance
    current_date = start_date_obj.replace(day=1)

    while current_date <= end_date_obj:
        month_key = current_date.strftime('%Y-%m')
        running_balance += monthly_net.get(month_key, 0.0)
        months.append({
            'month': month_key,
            'month_name': current_date.strftime('%b %Y'),
            'balance': running_balance
        })
        current_date += relativedelta(months=1)

    return {
        'start_date': start_date_obj.isoformat(),
        'end_date': end_date_obj.isoformat(),
        'months': months
    }
