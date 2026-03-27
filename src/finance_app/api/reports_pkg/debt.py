"""
Debt report endpoints: balance history, principal timeline, summary, payoff projection.
"""
import logging
from typing import Optional
from datetime import date
from dateutil.relativedelta import relativedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models import Debt, DebtPayment, Currency
from finance_app.services.debt.balance_service import (
    calculate_debt_balance_as_of,
    calculate_mortgage_principal_balance,
)
from finance_app.services.mortgage.service import calculate_monthly_payment
from finance_app.services.debt.amortization_service import (
    ensure_debt_amortization_records,
    fetch_amortization_for_month,
    fetch_amortization_range,
)
from finance_app.services.debt.timeline import build_debt_principal_timeline
from finance_app.domain.fx.service import convert_to_cop

from .common import get_exchange_rate, convert_to_currency

router = APIRouter()
logger = logging.getLogger(__name__)


def _calculate_debt_balance(
    db: Session, debt: Debt, as_of_date: date, today: date, include_projection: bool = True
) -> float:
    return calculate_debt_balance_as_of(
        db=db, debt=debt, as_of_date=as_of_date, today=today, include_projection=include_projection,
    )


def _log_debt_mismatch(context: str, legacy_total: float, canonical_total: float) -> None:
    if abs(legacy_total - canonical_total) > 0.01:
        logger.error(
            "Debt principal mismatch in %s: legacy=%s canonical=%s",
            context, round(legacy_total, 2), round(canonical_total, 2),
        )


@router.get("/debt-balance-history")
def get_debt_balance_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    projection_months: int = 0,
    include_full_history: bool = False,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """Get total debt balance over time using debt payments history."""
    debts = db.query(Debt).all()
    if not debts:
        return {'monthly': [], 'currency': None, 'current_total_debt': 0}

    today = date.today()
    if not end_date:
        end_date_obj = today
    else:
        end_date_obj = date.fromisoformat(end_date)

    if include_full_history or not start_date:
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
    if projection_months and projection_months > 0:
        end_date_obj = end_date_obj + relativedelta(months=projection_months)

    monthly_totals = []
    debt_types = sorted({debt.debt_type or 'Sin tipo' for debt in debts})
    current_date = start_date_obj
    current_month = today.replace(day=1)

    ensure_debt_amortization_records(db, start_date_obj, end_date_obj)
    amortization_records = fetch_amortization_range(
        db, start_date_obj, end_date_obj, [debt.id for debt in debts],
    )

    while current_date <= end_date_obj:
        debt_by_type = {debt_type: 0.0 for debt_type in debt_types}
        total_debt = 0.0

        for debt in debts:
            has_amortization_terms = bool(debt.term_months or debt.monthly_payment or debt.loan_years)
            record = amortization_records.get((debt.id, current_date))
            if record and has_amortization_terms and float(record.principal_remaining) > 0:
                principal = float(record.principal_remaining)
            elif debt.debt_type == "credit_card":
                principal = float(debt.current_balance or 0.0)
            elif debt.start_date and current_date >= debt.start_date.replace(day=1):
                # Fallback for debts without valid amortization terms
                principal = float(debt.current_balance or 0.0)
            else:
                continue
            principal_cop = float(convert_to_cop(principal, debt.currency_code, current_date, db=db))
            total_debt += principal_cop
            debt_by_type[debt.debt_type] = debt_by_type.get(debt.debt_type, 0.0) + principal_cop

        monthly_totals.append({
            'month': current_date.strftime('%Y-%m'),
            'month_name': current_date.strftime('%b %Y'),
            'total_debt': round(total_debt, 2),
            'debt_by_type': {key: round(value, 2) for key, value in debt_by_type.items()}
        })
        current_date += relativedelta(months=1)

    legacy_total = sum(_calculate_debt_balance(db, debt, today, today) for debt in debts)
    ensure_debt_amortization_records(db, current_month, current_month)
    amortization_map = fetch_amortization_for_month(db, current_month, [debt.id for debt in debts])
    canonical_total = sum(entry.principal_remaining for entry in amortization_map.values())
    _log_debt_mismatch("debt-balance-history", legacy_total, canonical_total)

    currency = db.query(Currency).filter_by(code="COP").first()
    current_month_key = date.today().strftime('%Y-%m')
    current_total = next(
        (item['total_debt'] for item in monthly_totals if item['month'] == current_month_key),
        monthly_totals[-1]['total_debt'] if monthly_totals else 0
    )

    return {
        'monthly': monthly_totals,
        'current_total_debt': current_total,
        'starting_total_debt': monthly_totals[0]['total_debt'] if monthly_totals else 0,
        'projected_total_debt': monthly_totals[-1]['total_debt'] if monthly_totals else 0,
        'debt_types': debt_types,
        'currency': currency.to_dict() if currency else None
    }


@router.get("/debt-principal-timeline")
def get_debt_principal_timeline(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    projection_months: int = 12,
    include_full_history: bool = False,
    include_projection: bool = True,
    currency_id: int = 1,
    db: Session = Depends(get_db),
):
    """Get monthly principal timeline for non-revolving debts."""
    debts = db.query(Debt).all()
    if not debts:
        return {"monthly": [], "debts": [], "currency": None, "current_total_principal": 0}

    today = date.today()
    if not end_date:
        end_date_obj = today
    else:
        end_date_obj = date.fromisoformat(end_date)

    if include_full_history or not start_date:
        earliest_dates = []
        for debt in debts:
            if debt.start_date:
                earliest_dates.append(debt.start_date)
            if debt.payments:
                earliest_dates.append(min(p.payment_date for p in debt.payments if p.payment_date))
        start_date_obj = min(earliest_dates) if earliest_dates else today
    else:
        start_date_obj = date.fromisoformat(start_date)

    start_month = start_date_obj.replace(day=1)
    end_month = end_date_obj.replace(day=1)
    if projection_months and projection_months > 0 and include_projection:
        end_month = end_month + relativedelta(months=projection_months)

    exchange_rate = get_exchange_rate(db)
    currencies = db.query(Currency).all()
    currency_map = {currency.code: currency.id for currency in currencies}

    timeline = build_debt_principal_timeline(
        start_month, end_month, debts,
        include_projection=include_projection,
        currency_id=currency_id,
        exchange_rate=exchange_rate,
        currency_map=currency_map,
        today=today,
    )

    currency = db.query(Currency).get(currency_id)
    debt_meta = [
        {"id": debt.id, "name": debt.name, "debt_type": debt.debt_type, "currency_code": debt.currency_code}
        for debt in debts
    ]

    current_month_key = date.today().strftime('%Y-%m')
    current_total = next(
        (item["total_principal_end"] for item in timeline if item["month"] == current_month_key),
        timeline[-1]["total_principal_end"] if timeline else 0,
    )

    return {
        "monthly": timeline,
        "debts": debt_meta,
        "current_total_principal": current_total,
        "starting_total_principal": timeline[0]["total_principal_end"] if timeline else 0,
        "projected_total_principal": timeline[-1]["total_principal_end"] if timeline else 0,
        "currency": currency.to_dict() if currency else None,
    }


@router.get("/debt-summary")
def get_debt_summary(
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """Summary of all active debts with amortization info."""
    exchange_rate = get_exchange_rate(db)
    debts = db.query(Debt).filter(Debt.is_active == True).all()
    currencies = db.query(Currency).all()
    currency_map = {currency.code: currency.id for currency in currencies}

    debt_details = []
    total_debt = 0
    total_original = 0
    total_monthly_payment = 0
    total_interest_paid = 0
    projected_total = 0
    today = date.today()
    projection_end = today + relativedelta(months=12)
    current_month = today.replace(day=1)
    projection_end_month = projection_end.replace(day=1)
    ensure_debt_amortization_records(db, current_month, projection_end_month)
    amortization_map = fetch_amortization_for_month(db, current_month)
    projected_map = fetch_amortization_for_month(db, projection_end_month)

    for debt in debts:
        debt_currency_id = currency_map.get(debt.currency_code, currency_id)
        if debt.debt_type == "mortgage":
            current_balance_original = calculate_mortgage_principal_balance(db, debt, as_of_date=today)
            projected_balance_original = current_balance_original
        else:
            has_amortization_terms = bool(debt.term_months or debt.monthly_payment or debt.loan_years)
            record = amortization_map.get(debt.id)
            current_balance_original = (
                float(record.principal_remaining)
                if record and has_amortization_terms and float(record.principal_remaining) > 0
                else (debt.current_balance or 0.0)
            )
            projected_record = projected_map.get(debt.id)
            projected_balance_original = (
                float(projected_record.principal_remaining) if projected_record else current_balance_original
            )
        original_amount_raw = debt.original_amount or 0

        current_balance = convert_to_currency(current_balance_original, debt_currency_id, currency_id, exchange_rate)
        monthly_payment = convert_to_currency(debt.monthly_payment or 0, debt_currency_id, currency_id, exchange_rate)
        original_amount = convert_to_currency(original_amount_raw, debt_currency_id, currency_id, exchange_rate)
        projected_balance = convert_to_currency(projected_balance_original, debt_currency_id, currency_id, exchange_rate)

        debt_payments = db.query(DebtPayment).filter(DebtPayment.debt_id == debt.id).all()
        interest_paid = sum(
            convert_to_currency(payment.interest or 0, debt_currency_id, currency_id, exchange_rate)
            for payment in debt_payments
        )

        if monthly_payment > 0 and current_balance > 0:
            months_remaining = current_balance / monthly_payment
        else:
            months_remaining = 0

        payoff_date = None
        if months_remaining > 0:
            payoff_date = (date.today() + relativedelta(months=int(months_remaining))).isoformat()

        debt_details.append({
            'id': debt.id,
            'name': debt.name,
            'type': debt.debt_type,
            'institution': debt.institution,
            'current_balance': round(current_balance, 2),
            'original_amount': round(original_amount, 2),
            'monthly_payment': round(monthly_payment, 2),
            'interest_rate': debt.interest_rate,
            'interest_paid': round(interest_paid, 2),
            'months_remaining': round(months_remaining, 1),
            'payoff_date': payoff_date,
            'start_date': debt.start_date.isoformat() if debt.start_date else None,
            'payment_day': debt.payment_day,
            'projected_balance': round(projected_balance, 2)
        })

        total_debt += current_balance
        total_original += original_amount
        total_monthly_payment += monthly_payment
        total_interest_paid += interest_paid
        projected_total += projected_balance

    debt_details.sort(key=lambda x: x['current_balance'], reverse=True)

    legacy_total = sum(_calculate_debt_balance(db, debt, today, today) for debt in debts)
    ensure_debt_amortization_records(db, current_month, current_month)
    amortization_map = fetch_amortization_for_month(db, current_month, [debt.id for debt in debts])
    canonical_total = sum(entry.principal_remaining for entry in amortization_map.values())
    _log_debt_mismatch("debt-summary", legacy_total, canonical_total)

    currency = db.query(Currency).get(currency_id)

    return {
        'debts': debt_details,
        'totals': {
            'total_debt': round(total_debt, 2),
            'total_original': round(total_original, 2),
            'total_projected': round(projected_total, 2),
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
    """Project debt payoff schedule with optional extra payments."""
    debt = db.query(Debt).get(debt_id)
    if not debt:
        raise HTTPException(status_code=404, detail="Debt not found")

    exchange_rate = get_exchange_rate(db)

    current_balance = convert_to_currency(
        debt.current_balance or 0, debt.currency_code, currency_id, exchange_rate
    )
    monthly_payment = convert_to_currency(
        debt.monthly_payment or 0, debt.currency_code, currency_id, exchange_rate
    ) + extra_payment

    interest_rate = debt.interest_rate or 0
    monthly_interest_rate = (interest_rate / 100) / 12

    schedule = []
    balance = current_balance
    month = 1
    total_interest = 0
    total_principal = 0

    while balance > 0 and month <= 360:
        interest_payment = balance * monthly_interest_rate
        principal_payment = min(monthly_payment - interest_payment, balance)

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
