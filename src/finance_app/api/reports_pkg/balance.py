"""
Balance trend and account balance history endpoints.
"""
from typing import Optional
from datetime import date
from dateutil.relativedelta import relativedelta

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_

from finance_app.database import get_db
from finance_app.models import Transaction, Account

from .common import get_exchange_rate, parse_date_range, convert_to_currency

router = APIRouter()


@router.get("/balance-trend")
def get_balance_trend(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """Get total account balance trend over time for active accounts."""
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
        Transaction.amount, Transaction.currency_id, Transaction.date
    ).filter(
        and_(Transaction.account_id.in_(account_ids), Transaction.date >= start_date_obj)
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
            Transaction.amount, Transaction.currency_id
        ).filter(
            and_(Transaction.account_id == account.id, Transaction.date >= created_date)
        ).all()

        net_after_creation = sum(
            convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
            for t in transactions_after_creation
        )
        initial_balance = convert_to_currency(
            account.balance, account.currency_id, currency_id, exchange_rate
        ) - net_after_creation
        start_balance -= initial_balance

        month_key = created_date.strftime('%Y-%m')
        initial_balance_adjustments[month_key] = (
            initial_balance_adjustments.get(month_key, 0.0) + initial_balance
        )

    transactions_in_range = db.query(
        Transaction.amount, Transaction.currency_id, Transaction.date
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
            transaction.amount, transaction.currency_id, currency_id, exchange_rate
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
    """Get total account balances over time. Interval: daily or monthly."""
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
        Transaction.amount, Transaction.currency_id, Transaction.date
    ).filter(
        and_(Transaction.account_id.in_(account_ids), Transaction.date >= start_date_obj)
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
            Transaction.amount, Transaction.currency_id
        ).filter(
            and_(Transaction.account_id == account.id, Transaction.date >= created_date)
        ).all()

        net_after_creation = sum(
            convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
            for t in transactions_after_creation
        )
        initial_balance = convert_to_currency(
            account.balance, account.currency_id, currency_id, exchange_rate
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
        Transaction.amount, Transaction.currency_id, Transaction.date
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
            transaction.amount, transaction.currency_id, currency_id, exchange_rate
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
