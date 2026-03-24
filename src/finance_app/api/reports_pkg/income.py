"""
Income, budget comparison, and summary report endpoints.
"""
from typing import Optional
from datetime import date
from dateutil.relativedelta import relativedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from finance_app.database import get_db
from finance_app.models import (
    Transaction, Category, Currency, BudgetMonth, Account, Payee,
)
from finance_app.services.budget_service import (
    build_income_transactions_query,
    build_spent_transactions_query,
)

from .common import get_exchange_rate, parse_date_range, convert_to_currency

router = APIRouter()


def get_income_total(
    db: Session,
    start_date: date,
    end_date: date,
    currency_id: int,
    exchange_rate: float,
    category_id: Optional[int] = None,
) -> float:
    income_transactions = build_income_transactions_query(
        db, start_date, end_date, category_id=category_id
    ).with_entities(Transaction.amount, Transaction.currency_id).all()

    return sum(
        convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
        for t in income_transactions
    )


def get_monthly_income(
    db: Session, year: int, month: int, currency_id: int, exchange_rate: float
) -> float:
    month_start = date(year, month, 1)
    month_end = month_start + relativedelta(months=1)
    return get_income_total(db, month_start, month_end, currency_id, exchange_rate)


def get_budget_report_income_total(
    db: Session,
    start_date: date,
    end_date: date,
    currency_id: int,
    exchange_rate: float,
    excluded_payee_name: str = "Balance Adjustment",
) -> float:
    income_transactions = db.query(Transaction).outerjoin(Payee).filter(
        Transaction.date >= start_date,
        Transaction.date < end_date,
        Transaction.amount > 0,
        Transaction.transfer_account_id.is_(None),
        Transaction.is_adjustment.is_(False),
        or_(Payee.name.is_(None), Payee.name != excluded_payee_name),
    ).with_entities(Transaction.amount, Transaction.currency_id).all()

    return sum(
        convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
        for t in income_transactions
    )


@router.get("/income-vs-expenses")
def get_income_vs_expenses(
    months: int = 6,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """Get income vs expenses for the last N months."""
    end_date = date.today()
    start_date = end_date - relativedelta(months=months)
    min_start_date = date(2026, 1, 1)
    note = None
    if start_date < min_start_date:
        start_date = min_start_date
        note = 'Los datos anteriores a enero de 2026 no se pueden mostrar porque no se tiene registro.'

    exchange_rate = get_exchange_rate(db)
    results = []
    current_date = start_date.replace(day=1)

    while current_date <= end_date:
        month_start = current_date
        month_end = current_date + relativedelta(months=1)

        income = get_budget_report_income_total(db, month_start, month_end, currency_id, exchange_rate)

        expense_transactions = build_spent_transactions_query(db, month_start, month_end).with_entities(
            Transaction.amount, Transaction.currency_id
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
    """Get budget vs income vs expenses over time."""
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
            budget_month.assigned or 0, budget_month.currency_id, currency_id, exchange_rate
        )
        budget_totals[month_key] = budget_totals.get(month_key, 0) + budgeted_converted

    results = []
    current_date = start_date.replace(day=1)

    while current_date <= end_date:
        month_start = current_date
        month_end = current_date + relativedelta(months=1)

        income = get_budget_report_income_total(db, month_start, month_end, currency_id, exchange_rate)

        expense_transactions = build_spent_transactions_query(db, month_start, month_end).with_entities(
            Transaction.amount, Transaction.currency_id
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
            'expenses': expenses,
            'net_balance': income - expenses
        })
        current_date += relativedelta(months=1)

    currency = db.query(Currency).get(currency_id)

    return {
        'months': results,
        'period': f'{start_date.strftime("%b %Y")} - {end_date.strftime("%b %Y")}',
        'note': note,
        'currency': currency.to_dict() if currency else None
    }


@router.get("/top-income-expenses")
def get_top_income_expenses(
    months: int = 12,
    currency_id: int = 1,
    limit: int = 5,
    db: Session = Depends(get_db)
):
    """Get top income and expense categories for the last N months."""
    end_date = date.today()
    start_date = end_date - relativedelta(months=months)
    min_start_date = date(2026, 1, 1)
    note = None
    if start_date < min_start_date:
        start_date = min_start_date
        note = 'Los datos anteriores a enero de 2026 no se pueden mostrar porque no se tiene registro.'

    exchange_rate = get_exchange_rate(db)
    end_date_exclusive = end_date + relativedelta(days=1)

    income_rows = build_income_transactions_query(db, start_date, end_date_exclusive).with_entities(
        Transaction.amount, Transaction.currency_id, Category.name.label('category_name')
    ).all()

    income_totals = {}
    for row in income_rows:
        category_name = row.category_name or 'Sin categoría'
        converted_amount = convert_to_currency(row.amount, row.currency_id, currency_id, exchange_rate)
        income_totals[category_name] = income_totals.get(category_name, 0) + converted_amount

    income_results = [{'category': cn, 'amount': total} for cn, total in income_totals.items()]
    income_results.sort(key=lambda item: item['amount'], reverse=True)

    expense_rows = build_spent_transactions_query(db, start_date, end_date_exclusive).with_entities(
        Transaction.amount, Transaction.currency_id, Category.name.label('category_name')
    ).all()

    expense_totals = {}
    for row in expense_rows:
        category_name = row.category_name or 'Sin categoría'
        converted_amount = convert_to_currency(abs(row.amount), row.currency_id, currency_id, exchange_rate)
        expense_totals[category_name] = expense_totals.get(category_name, 0) + converted_amount

    expense_results = [{'category': cn, 'amount': total} for cn, total in expense_totals.items()]
    expense_results.sort(key=lambda item: item['amount'], reverse=True)

    return {
        'period': f'{start_date.strftime("%b %Y")} - {end_date.strftime("%b %Y")}',
        'note': note,
        'income': income_results[:limit],
        'expenses': expense_results[:limit]
    }


@router.get("/budget-vs-actual")
def get_budget_vs_actual(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """Compare budgeted amounts vs actual spending by category."""
    today = date.today()
    start_date_obj = today.replace(day=1) - relativedelta(months=1)
    end_date_obj = today.replace(day=1) - relativedelta(days=1)
    exchange_rate = get_exchange_rate(db)

    budget_data = db.query(BudgetMonth).filter(
        and_(
            BudgetMonth.month >= start_date_obj,
            BudgetMonth.month <= end_date_obj
        )
    ).all()

    category_summary = {}
    for budget_month in budget_data:
        cat_id = budget_month.category_id
        if cat_id not in category_summary:
            category = db.query(Category).get(cat_id)
            category_summary[cat_id] = {
                'category_id': cat_id,
                'category_name': category.name if category else 'Unknown',
                'category_group': category.category_group.name if category and category.category_group else 'Unknown',
                'budgeted': 0,
                'actual': 0,
                'difference': 0,
                'percentage': 0
            }

        budgeted_converted = convert_to_currency(
            budget_month.assigned or 0, budget_month.currency_id, currency_id, exchange_rate
        )
        category_summary[cat_id]['budgeted'] += budgeted_converted

        month_start = budget_month.month
        month_end = month_start + relativedelta(months=1)
        actual_transactions = build_spent_transactions_query(
            db, month_start, month_end, category_id=cat_id
        ).with_entities(Transaction.amount, Transaction.currency_id).all()

        actual_spent = sum(
            convert_to_currency(abs(t.amount), t.currency_id, currency_id, exchange_rate)
            for t in actual_transactions
        )
        category_summary[cat_id]['actual'] += actual_spent

    results = []
    for cat_id, data in category_summary.items():
        difference = data['budgeted'] - data['actual']
        percentage = (data['actual'] / data['budgeted'] * 100) if data['budgeted'] > 0 else 0
        data['difference'] = difference
        data['percentage'] = round(percentage, 2)
        data['status'] = 'under' if difference > 0 else ('over' if difference < 0 else 'exact')
        results.append(data)

    results.sort(key=lambda x: x['difference'])
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


@router.get("/savings-rate")
def get_savings_rate(
    months: int = 12,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """Calculate savings rate (Income - Expenses) / Income * 100."""
    end_date = date.today()
    start_date = end_date - relativedelta(months=months)
    min_start_date = date(2026, 1, 1)
    if start_date < min_start_date:
        start_date = min_start_date

    exchange_rate = get_exchange_rate(db)
    monthly_data = []
    current_date = start_date.replace(day=1)

    while current_date <= end_date:
        month_start = current_date
        month_end = current_date + relativedelta(months=1)

        income = get_monthly_income(db, month_start.year, month_start.month, currency_id, exchange_rate)
        expense_transactions = build_spent_transactions_query(db, month_start, month_end).with_entities(
            Transaction.amount, Transaction.currency_id
        ).all()
        expenses = sum(
            convert_to_currency(abs(t.amount), t.currency_id, currency_id, exchange_rate)
            for t in expense_transactions
        )

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


@router.get("/summary")
def get_summary(
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """Get overall financial summary."""
    today = date.today()
    month_start = today.replace(day=1)
    month_end = today + relativedelta(days=1)
    exchange_rate = get_exchange_rate(db)

    month_income = get_income_total(db, month_start, month_end, currency_id, exchange_rate)

    expense_transactions = build_spent_transactions_query(db, month_start, month_end).with_entities(
        Transaction.amount, Transaction.currency_id
    ).all()
    month_expenses = sum(
        convert_to_currency(abs(t.amount), t.currency_id, currency_id, exchange_rate)
        for t in expense_transactions
    )

    accounts = db.query(Account).filter(Account.is_closed == False).all()
    total_balance = sum(
        convert_to_currency(acc.balance, acc.currency_id, currency_id, exchange_rate)
        for acc in accounts
    )
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
    """Get income, expenses, and average monthly expenses for a period."""
    start_date_obj, end_date_obj = parse_date_range(start_date, end_date)
    exchange_rate = get_exchange_rate(db)
    end_date_exclusive = end_date_obj + relativedelta(days=1)

    expense_transactions = build_spent_transactions_query(db, start_date_obj, end_date_exclusive).with_entities(
        Transaction.amount, Transaction.currency_id
    ).all()

    total_income = get_income_total(db, start_date_obj, end_date_exclusive, currency_id, exchange_rate)
    total_expenses = sum(
        convert_to_currency(abs(t.amount), t.currency_id, currency_id, exchange_rate)
        for t in expense_transactions
    )

    months_count = (end_date_obj.year - start_date_obj.year) * 12 + (end_date_obj.month - start_date_obj.month) + 1
    average_monthly_expenses = total_expenses / months_count if months_count > 0 else 0
    currency = db.query(Currency).get(currency_id)

    # Compute previous period of same length for trend comparison
    period_days = (end_date_obj - start_date_obj).days + 1
    prev_end = start_date_obj - relativedelta(days=1)
    prev_start = prev_end - relativedelta(days=period_days - 1)
    min_start_date = date(2026, 1, 1)

    prev_income = 0.0
    prev_expenses = 0.0
    if prev_start >= min_start_date:
        prev_end_exclusive = prev_end + relativedelta(days=1)
        prev_income = get_income_total(db, prev_start, prev_end_exclusive, currency_id, exchange_rate)
        prev_expense_txs = build_spent_transactions_query(db, prev_start, prev_end_exclusive).with_entities(
            Transaction.amount, Transaction.currency_id
        ).all()
        prev_expenses = sum(
            convert_to_currency(abs(t.amount), t.currency_id, currency_id, exchange_rate)
            for t in prev_expense_txs
        )

    def _trend(current, previous):
        if previous == 0:
            return {"direction": "neutral", "change_pct": 0}
        pct = round((current - previous) / abs(previous) * 100, 1)
        direction = "up" if pct > 0 else "down" if pct < 0 else "neutral"
        return {"direction": direction, "change_pct": pct}

    return {
        'start_date': start_date_obj.isoformat(),
        'end_date': end_date_obj.isoformat(),
        'total_income': total_income,
        'total_expenses': total_expenses,
        'average_monthly_expenses': average_monthly_expenses,
        'income_trend': _trend(total_income, prev_income),
        'expense_trend': _trend(total_expenses, prev_expenses),
        'currency': currency.to_dict() if currency else None
    }
