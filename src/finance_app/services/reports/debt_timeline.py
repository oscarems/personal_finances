"""
Debt principal timeline builder.

Extracted from the monolithic reports module to keep business logic
separate from HTTP endpoint definitions.
"""
import calendar
from datetime import date
from typing import Optional, Tuple, Iterable, List, Dict

from dateutil.relativedelta import relativedelta

from finance_app.models import Debt


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _month_end(day: date) -> date:
    return day.replace(day=1) + relativedelta(months=1) - relativedelta(days=1)


def _month_key(day: date) -> Tuple[int, int]:
    return day.year, day.month


def _iter_months(start_month: date, end_month: date) -> Iterable[date]:
    current = start_month
    while current <= end_month:
        yield current
        current = current + relativedelta(months=1)


def _adjust_to_payment_day(base_date: date, payment_day: Optional[int]) -> date:
    if not payment_day:
        return base_date
    last_day = calendar.monthrange(base_date.year, base_date.month)[1]
    return base_date.replace(day=min(payment_day, last_day))


def _infer_monthly_payment(
    payments_by_month: Dict[Tuple[int, int], Dict[str, float]],
    today: date,
    months: int = 6,
) -> float:
    end_month = _month_start(today) - relativedelta(months=1)
    totals = []
    for offset in range(months):
        month = end_month - relativedelta(months=offset)
        total = payments_by_month.get(_month_key(month), {}).get("amount", 0.0)
        if total > 0:
            totals.append(total)
    if not totals:
        return 0.0
    return sum(totals) / len(totals)


def _annual_rate_decimal(debt: Debt) -> float:
    if debt.annual_interest_rate is not None:
        try:
            rate = float(debt.annual_interest_rate)
        except (TypeError, ValueError):
            rate = 0.0
        return rate / 100 if rate > 1 else rate
    if debt.interest_rate:
        return debt.interest_rate / 100
    return 0.0


def _monthly_rate(annual_rate: float) -> float:
    if not annual_rate:
        return 0.0
    return (1 + annual_rate) ** (1 / 12) - 1


def convert_to_currency(amount: float, from_currency_id: int, to_currency_id: int, exchange_rate: float) -> float:
    if from_currency_id == to_currency_id:
        return amount
    if from_currency_id == 2 and to_currency_id == 1:
        return amount * exchange_rate
    if from_currency_id == 1 and to_currency_id == 2:
        return amount / exchange_rate
    return amount


def build_debt_principal_timeline(
    start_month: date,
    end_month: date,
    debts: List[Debt],
    include_projection: bool = True,
    currency_id: int = 1,
    exchange_rate: float = 1.0,
    currency_map: Optional[Dict[str, int]] = None,
    today: Optional[date] = None,
) -> List[dict]:
    if today is None:
        today = date.today()
    current_month = _month_start(today)
    if not include_projection and end_month > current_month:
        end_month = current_month

    debt_states: Dict[int, float] = {}
    payment_lookup: Dict[int, Dict[Tuple[int, int], Dict[str, float]]] = {}
    inferred_payments: Dict[int, float] = {}

    for debt in debts:
        payments_by_month: Dict[Tuple[int, int], Dict[str, float]] = {}
        for payment in debt.payments:
            if not payment.payment_date:
                continue
            key = _month_key(payment.payment_date)
            bucket = payments_by_month.setdefault(key, {"amount": 0.0, "principal": 0.0})
            bucket["amount"] += payment.amount or 0.0
            if payment.principal:
                bucket["principal"] += payment.principal
        payment_lookup[debt.id] = payments_by_month
        inferred_payments[debt.id] = _infer_monthly_payment(payments_by_month, today)

    timeline = []
    for month_start_date in _iter_months(start_month, end_month):
        month_end_date = month_start_date + relativedelta(months=1) - relativedelta(days=1)
        is_projection = month_start_date > current_month
        month_entry = {
            "month": month_start_date.strftime("%Y-%m"),
            "month_name": month_start_date.strftime("%b %Y"),
            "is_projection": is_projection,
            "debts": {},
            "total_principal_end": 0.0,
        }

        for debt in debts:
            if debt.debt_type == "credit_card":
                continue
            if debt.start_date and month_end_date < debt.start_date:
                month_entry["debts"][str(debt.id)] = {
                    "principal_start": 0.0,
                    "interest_accrued": 0.0,
                    "payment_applied": 0.0,
                    "principal_paid": 0.0,
                    "principal_end": 0.0,
                }
                continue

            if debt.id not in debt_states:
                initial_balance = debt.original_amount if debt.original_amount is not None else debt.current_balance or 0.0
                debt_states[debt.id] = max(0.0, initial_balance)

            principal_start = debt_states[debt.id]
            interest_accrued = 0.0

            if is_projection and include_projection:
                payment_applied = debt.monthly_payment or inferred_payments.get(debt.id, 0.0)
                principal_paid = max(0.0, payment_applied)
            else:
                mk = _month_key(month_start_date)
                payment_data = payment_lookup.get(debt.id, {}).get(mk, {})
                payment_applied = payment_data.get("amount", 0.0)
                explicit_principal = payment_data.get("principal", 0.0)
                if explicit_principal > 0:
                    principal_paid = min(explicit_principal, principal_start)
                else:
                    principal_paid = max(0.0, payment_applied)

            principal_paid = min(principal_paid, principal_start)
            principal_end = max(0.0, principal_start - principal_paid)
            debt_states[debt.id] = principal_end

            debt_currency_id = currency_map.get(debt.currency_code, currency_id) if currency_map else currency_id
            principal_start_conv = convert_to_currency(principal_start, debt_currency_id, currency_id, exchange_rate)
            interest_conv = convert_to_currency(interest_accrued, debt_currency_id, currency_id, exchange_rate)
            payment_conv = convert_to_currency(payment_applied, debt_currency_id, currency_id, exchange_rate)
            principal_paid_conv = convert_to_currency(principal_paid, debt_currency_id, currency_id, exchange_rate)
            principal_end_conv = convert_to_currency(principal_end, debt_currency_id, currency_id, exchange_rate)

            month_entry["debts"][str(debt.id)] = {
                "principal_start": round(principal_start_conv, 2),
                "interest_accrued": round(interest_conv, 2),
                "payment_applied": round(payment_conv, 2),
                "principal_paid": round(principal_paid_conv, 2),
                "principal_end": round(principal_end_conv, 2),
            }
            month_entry["total_principal_end"] += principal_end_conv

        month_entry["total_principal_end"] = round(month_entry["total_principal_end"], 2)
        timeline.append(month_entry)

    return timeline
