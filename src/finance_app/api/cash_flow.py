"""
Cash Flow Forecast API

Projects account balances for the next N days using:
- Current account balances
- Upcoming recurring transactions
- Upcoming debt payments
- Goal contributions (optional)
"""
from datetime import date, timedelta
from typing import Optional
from dateutil.relativedelta import relativedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models import Account, RecurringTransaction, Debt, Goal
from finance_app.services.exchange_rate_service import get_current_exchange_rate
from finance_app.services.recurring_service import (
    get_next_scheduled_date,
    get_next_occurrence_date,
)

router = APIRouter()


def _get_exchange_rate(db: Session) -> float:
    return get_current_exchange_rate(db)


def _to_cop(amount: float, currency_code: str, rate: float) -> float:
    if currency_code == "USD":
        return amount * rate
    return amount


def _collect_recurring_events(
    db: Session,
    today: date,
    until: date,
    exchange_rate: float,
) -> list[dict]:
    """Generate all upcoming recurring transaction events in [today+1, until]."""
    events = []
    active = db.query(RecurringTransaction).filter(RecurringTransaction.is_active == True).all()

    for r in active:
        # Start from next scheduled occurrence
        next_date = get_next_scheduled_date(r)
        if next_date is None:
            continue

        # Walk through all occurrences in the forecast window
        current = next_date
        iterations = 0
        while current <= until and iterations < 500:
            iterations += 1
            if current > today:
                signed = r.amount
                if r.transaction_type:
                    base = abs(r.amount)
                    signed = base if r.transaction_type == "income" else -base

                currency = "COP"
                if r.currency_id == 2:
                    currency = "USD"

                amount_cop = _to_cop(abs(signed), currency, exchange_rate)
                label = r.description or "Recurrente"
                payee = r.payee.name if r.payee else None

                events.append({
                    "date": current.isoformat(),
                    "label": payee or label,
                    "type": "income" if signed > 0 else "expense",
                    "source": "recurring",
                    "amount_signed": signed,
                    "amount_cop": amount_cop if signed > 0 else -amount_cop,
                    "currency": currency,
                })

            current = get_next_occurrence_date(r, current)

    return events


def _collect_debt_events(
    db: Session,
    today: date,
    until: date,
    exchange_rate: float,
) -> list[dict]:
    """Generate upcoming debt payment events based on payment_day or next_due_date.

    For credit cards, uses minimum_payment as fallback when monthly_payment is not set.
    """
    events = []
    debts = db.query(Debt).filter(Debt.is_active == True).all()

    for debt in debts:
        # Determine the scheduled payment amount.
        # Credit cards: prefer monthly_payment, fall back to minimum_payment.
        # Other types: monthly_payment is required.
        if debt.debt_type == "credit_card":
            amount_raw = debt.monthly_payment or debt.minimum_payment
        else:
            amount_raw = debt.monthly_payment

        if not amount_raw or amount_raw <= 0:
            continue

        payment_day = debt.payment_day or (debt.next_due_date.day if debt.next_due_date else None)
        if not payment_day:
            continue

        # Build monthly occurrences
        # Start from next occurrence after today
        candidate_month = today.replace(day=1)
        iterations = 0
        while iterations < 13:  # max 13 months ahead
            iterations += 1
            try:
                candidate = candidate_month.replace(day=int(payment_day))
            except ValueError:
                # Day doesn't exist in this month (e.g. Feb 30)
                candidate = (candidate_month + relativedelta(months=1)).replace(day=1) - timedelta(days=1)

            if today < candidate <= until:
                amount = float(amount_raw)
                currency = debt.currency_code or "COP"
                amount_cop = _to_cop(amount, currency, exchange_rate)
                label_suffix = " (mín)" if debt.debt_type == "credit_card" and not debt.monthly_payment else ""
                events.append({
                    "date": candidate.isoformat(),
                    "label": f"Pago: {debt.name}{label_suffix}",
                    "type": "debt_payment",
                    "source": "debt",
                    "amount_signed": -amount,
                    "amount_cop": -amount_cop,
                    "currency": currency,
                    "debt_id": debt.id,
                    "debt_type": debt.debt_type,
                })

            candidate_month = candidate_month + relativedelta(months=1)

    return events


@router.get("/forecast")
def get_cash_flow_forecast(
    days: int = Query(default=90, ge=7, le=365),
    currency_code: str = Query(default="COP"),
    db: Session = Depends(get_db),
):
    """
    Project account balances for the next `days` days.

    Returns:
    - events: list of upcoming transactions (recurring + debt payments)
    - daily_balance: cumulative balance projection per day
    - summary: income/expense totals for the period
    """
    today = date.today()
    until = today + timedelta(days=days)
    exchange_rate = _get_exchange_rate(db)

    # --- Starting balance: sum of budget accounts (exclude credit-type) ---
    excluded_types = {"credit_card", "credit_loan", "mortgage"}
    accounts = db.query(Account).filter(
        Account.is_budget == True,
        Account.is_closed == False,
    ).all()

    starting_balance_cop = 0.0
    for acc in accounts:
        if acc.type in excluded_types:
            continue
        currency = "USD" if (acc.currency and acc.currency.code == "USD") else "COP"
        starting_balance_cop += _to_cop(float(acc.balance or 0), currency, exchange_rate)

    # --- Collect events ---
    events = []
    events.extend(_collect_recurring_events(db, today, until, exchange_rate))
    events.extend(_collect_debt_events(db, today, until, exchange_rate))

    # Sort by date
    events.sort(key=lambda e: e["date"])

    # --- Build daily cumulative balance ---
    # Index events by date
    events_by_date: dict[str, list[dict]] = {}
    for ev in events:
        events_by_date.setdefault(ev["date"], []).append(ev)

    daily_balance = []
    running = starting_balance_cop
    current = today + timedelta(days=1)
    while current <= until:
        day_str = current.isoformat()
        day_events = events_by_date.get(day_str, [])
        day_delta = sum(e["amount_cop"] for e in day_events)
        running += day_delta
        daily_balance.append({
            "date": day_str,
            "balance": round(running, 2),
            "delta": round(day_delta, 2),
            "events": day_events,
        })
        current += timedelta(days=1)

    # --- Summary ---
    total_income = sum(e["amount_cop"] for e in events if e["amount_cop"] > 0)
    total_expense = sum(e["amount_cop"] for e in events if e["amount_cop"] < 0)

    return {
        "today": today.isoformat(),
        "until": until.isoformat(),
        "days": days,
        "starting_balance_cop": round(starting_balance_cop, 2),
        "currency": currency_code,
        "exchange_rate": exchange_rate,
        "events": events,
        "daily_balance": daily_balance,
        "summary": {
            "total_income": round(total_income, 2),
            "total_expense": round(total_expense, 2),
            "net": round(total_income + total_expense, 2),
            "ending_balance": round(starting_balance_cop + total_income + total_expense, 2),
        },
    }


@router.get("/upcoming")
def get_upcoming_events(
    days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
):
    """
    Returns the next upcoming financial events (recurring + debt payments)
    for the next `days` days. Used by the dashboard widget.
    """
    today = date.today()
    until = today + timedelta(days=days)
    exchange_rate = _get_exchange_rate(db)

    events = []
    events.extend(_collect_recurring_events(db, today, until, exchange_rate))
    events.extend(_collect_debt_events(db, today, until, exchange_rate))
    events.sort(key=lambda e: e["date"])

    return {"events": events, "today": today.isoformat()}
