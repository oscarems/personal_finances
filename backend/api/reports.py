"""
Reports and Analytics API
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_
from typing import Optional
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from backend.database import get_db
from backend.models import Transaction, Category, CategoryGroup, Account, Currency

router = APIRouter()


@router.get("/spending-by-category")
def get_spending_by_category(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Get spending grouped by category for a date range
    """
    # Default to current month if no dates provided
    if not start_date:
        start_date = date.today().replace(day=1).isoformat()
    if not end_date:
        end_date = date.today().isoformat()

    # Query transactions
    query = db.query(
        Category.name.label('category_name'),
        CategoryGroup.name.label('group_name'),
        func.sum(Transaction.amount).label('total')
    ).join(
        Category, Transaction.category_id == Category.id
    ).join(
        CategoryGroup, Category.category_group_id == CategoryGroup.id
    ).filter(
        and_(
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.currency_id == currency_id,
            Transaction.amount < 0  # Only expenses (negative amounts)
        )
    ).group_by(
        Category.name, CategoryGroup.name
    ).order_by(
        func.sum(Transaction.amount).asc()
    ).all()

    # Format results
    results = []
    for row in query:
        results.append({
            'category': row.category_name,
            'group': row.group_name,
            'amount': abs(row.total)  # Convert to positive for display
        })

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
    """
    # Default to current month if no dates provided
    if not start_date:
        start_date = date.today().replace(day=1).isoformat()
    if not end_date:
        end_date = date.today().isoformat()

    # Query transactions
    query = db.query(
        CategoryGroup.name.label('group_name'),
        func.sum(Transaction.amount).label('total')
    ).join(
        Category, Transaction.category_id == Category.id
    ).join(
        CategoryGroup, Category.category_group_id == CategoryGroup.id
    ).filter(
        and_(
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.currency_id == currency_id,
            Transaction.amount < 0  # Only expenses
        )
    ).group_by(
        CategoryGroup.name
    ).order_by(
        func.sum(Transaction.amount).asc()
    ).all()

    # Format results
    results = []
    for row in query:
        results.append({
            'group': row.group_name,
            'amount': abs(row.total)
        })

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
    """
    # Calculate start date (N months ago)
    end_date = date.today()
    start_date = end_date - relativedelta(months=months)

    # Query for monthly totals
    results = []
    current_date = start_date.replace(day=1)

    while current_date <= end_date:
        month_start = current_date
        month_end = current_date + relativedelta(months=1) - relativedelta(days=1)

        # Income (positive amounts)
        income = db.query(func.sum(Transaction.amount)).filter(
            and_(
                Transaction.date >= month_start,
                Transaction.date <= month_end,
                Transaction.currency_id == currency_id,
                Transaction.amount > 0
            )
        ).scalar() or 0

        # Expenses (negative amounts, convert to positive)
        expenses_raw = db.query(func.sum(Transaction.amount)).filter(
            and_(
                Transaction.date >= month_start,
                Transaction.date <= month_end,
                Transaction.currency_id == currency_id,
                Transaction.amount < 0
            )
        ).scalar() or 0
        expenses = abs(expenses_raw)

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
    """
    end_date = date.today()
    start_date = end_date - relativedelta(months=months)

    results = []
    current_date = start_date.replace(day=1)

    while current_date <= end_date:
        month_start = current_date
        month_end = current_date + relativedelta(months=1) - relativedelta(days=1)

        # Build query
        query = db.query(func.sum(Transaction.amount)).filter(
            and_(
                Transaction.date >= month_start,
                Transaction.date <= month_end,
                Transaction.currency_id == currency_id,
                Transaction.amount < 0  # Only expenses
            )
        )

        if category_id:
            query = query.filter(Transaction.category_id == category_id)

        total = abs(query.scalar() or 0)

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
    """
    today = date.today()
    month_start = today.replace(day=1)

    # Current month income
    month_income = db.query(func.sum(Transaction.amount)).filter(
        and_(
            Transaction.date >= month_start,
            Transaction.date <= today,
            Transaction.currency_id == currency_id,
            Transaction.amount > 0
        )
    ).scalar() or 0

    # Current month expenses
    month_expenses_raw = db.query(func.sum(Transaction.amount)).filter(
        and_(
            Transaction.date >= month_start,
            Transaction.date <= today,
            Transaction.currency_id == currency_id,
            Transaction.amount < 0
        )
    ).scalar() or 0
    month_expenses = abs(month_expenses_raw)

    # Account balances
    accounts = db.query(Account).filter(
        and_(
            Account.is_closed == False,
            Account.currency_id == currency_id
        )
    ).all()

    total_balance = sum(acc.balance for acc in accounts)

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
