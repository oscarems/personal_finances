"""
Spending report endpoints: by category, tag, trends.
"""
from typing import Optional
from datetime import date
from dateutil.relativedelta import relativedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from finance_app.database import get_db
from finance_app.models import Transaction, Category, TransactionTag
from finance_app.services.budget_service import build_spent_transactions_query

from .common import get_exchange_rate, parse_date_range, convert_to_currency, expense_allocations

router = APIRouter()


@router.get("/spending-by-category")
def get_spending_by_category(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """Get spending grouped by category for a date range."""
    start_date_obj, end_date_obj = parse_date_range(start_date, end_date)
    end_date_exclusive = end_date_obj + relativedelta(days=1)
    exchange_rate = get_exchange_rate(db)

    allocations = expense_allocations(db, start_date_obj, end_date_exclusive)

    category_totals = {}
    for tx, category, allocation_amount in allocations:
        group_name = category.category_group.name if category and category.category_group else "Sin grupo"
        category_name = category.name if category else "Sin categoría"
        key = (category_name, group_name)
        converted_amount = convert_to_currency(allocation_amount, tx.currency_id, currency_id, exchange_rate)
        if key not in category_totals:
            category_totals[key] = 0
        category_totals[key] += converted_amount

    results = [
        {'category': cat_name, 'group': grp_name, 'amount': total}
        for (cat_name, grp_name), total in category_totals.items()
    ]
    results.sort(key=lambda x: x['amount'], reverse=True)
    total_expenses = sum(r['amount'] for r in results)

    return {
        'start_date': start_date_obj.isoformat(),
        'end_date': end_date_obj.isoformat(),
        'total_expenses': total_expenses,
        'categories': results
    }


@router.get("/spending-by-tag")
def get_spending_by_tag(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currency_id: int = 1,
    category_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    start_date_obj, end_date_obj = parse_date_range(start_date, end_date)
    end_date_exclusive = end_date_obj + relativedelta(days=1)
    exchange_rate = get_exchange_rate(db)

    tx_query = build_spent_transactions_query(db, start_date_obj, end_date_exclusive).options(
        joinedload(Transaction.tag_links).joinedload(TransactionTag.tag),
        joinedload(Transaction.splits),
    )

    totals = {}
    uncategorized_key = "(sin tag)"
    for tx in tx_query.all():
        if category_id and tx.splits:
            alloc_amount = sum(abs(split.amount) for split in tx.splits if split.category_id == category_id)
            if alloc_amount == 0:
                continue
        elif category_id:
            if tx.category_id != category_id:
                continue
            alloc_amount = abs(tx.amount)
        else:
            alloc_amount = abs(tx.amount)

        converted = convert_to_currency(alloc_amount, tx.currency_id, currency_id, exchange_rate)
        tag_names = [link.tag.name for link in tx.tag_links if link.tag]
        if not tag_names:
            totals[uncategorized_key] = totals.get(uncategorized_key, 0.0) + converted
            continue
        for tag_name in tag_names:
            totals[tag_name] = totals.get(tag_name, 0.0) + converted

    rows = [{"tag": tag, "amount": amount} for tag, amount in totals.items()]
    rows.sort(key=lambda item: item["amount"], reverse=True)

    return {
        "start_date": start_date_obj.isoformat(),
        "end_date": end_date_obj.isoformat(),
        "currency_id": currency_id,
        "category_id": category_id,
        "total_expenses": round(sum(row["amount"] for row in rows), 2),
        "tags": rows,
    }


@router.get("/spending-trends")
def get_spending_trends(
    category_id: Optional[int] = None,
    months: int = 12,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """Get spending trends over time for a specific category or all categories."""
    end_date = date.today()
    start_date = end_date - relativedelta(months=months)
    exchange_rate = get_exchange_rate(db)

    results = []
    current_date = start_date.replace(day=1)

    while current_date <= end_date:
        month_start = current_date
        month_end = current_date + relativedelta(months=1)

        query = build_spent_transactions_query(db, month_start, month_end).with_entities(
            Transaction.amount,
            Transaction.currency_id
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


@router.get("/spending-by-category-over-time")
def get_spending_by_category_over_time(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currency_id: int = 1,
    top_n: int = 8,
    db: Session = Depends(get_db)
):
    """Get spending broken down by category for each month in the range."""
    start_date_obj, end_date_obj = parse_date_range(start_date, end_date)
    exchange_rate = get_exchange_rate(db)

    # Collect data per month per category
    months_list = []
    category_totals_global = {}
    current_date = start_date_obj.replace(day=1)

    while current_date <= end_date_obj:
        month_start = current_date
        month_end = current_date + relativedelta(months=1)

        allocations = expense_allocations(db, month_start, month_end)
        month_categories = {}
        for tx, category, allocation_amount in allocations:
            cat_name = category.name if category else "Sin categoría"
            converted = convert_to_currency(allocation_amount, tx.currency_id, currency_id, exchange_rate)
            month_categories[cat_name] = month_categories.get(cat_name, 0) + converted
            category_totals_global[cat_name] = category_totals_global.get(cat_name, 0) + converted

        months_list.append({
            'month': current_date.strftime('%Y-%m'),
            'month_name': current_date.strftime('%b %Y'),
            'categories': month_categories,
        })
        current_date += relativedelta(months=1)

    # Get top N categories by total spending
    top_categories = sorted(category_totals_global.items(), key=lambda x: x[1], reverse=True)[:top_n]
    top_cat_names = [c[0] for c in top_categories]

    # Build series per category
    series = []
    for cat_name in top_cat_names:
        series.append({
            'category': cat_name,
            'data': [m['categories'].get(cat_name, 0) for m in months_list],
        })

    return {
        'months': [m['month_name'] for m in months_list],
        'series': series,
    }
