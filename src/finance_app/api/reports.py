"""
Reports and Analytics API
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_
from typing import Optional, Tuple, Iterable, List, Dict
from datetime import date, datetime
import calendar
from dateutil.relativedelta import relativedelta

from finance_app.database import get_db
from finance_app.models import Transaction, Category, CategoryGroup, Account, Currency, ExchangeRate, BudgetMonth, Debt, DebtPayment, WealthAsset
from finance_app.utils.wealth import apply_expected_appreciation, apply_depreciation
from finance_app.services.mortgage_service import calculate_monthly_payment
from finance_app.services.real_estate_wealth_service import build_real_estate_wealth_timeline
from finance_app.services.budget_service import build_spent_transactions_query

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


def _adjust_to_payment_day(base_date: date, payment_day: Optional[int]) -> date:
    if not payment_day:
        return base_date
    last_day = calendar.monthrange(base_date.year, base_date.month)[1]
    return base_date.replace(day=min(payment_day, last_day))


def _payment_principal(payment: DebtPayment) -> float:
    if payment.principal is not None:
        return abs(payment.principal)
    if payment.amount is not None:
        interest = abs(payment.interest or 0.0)
        fees = abs(payment.fees or 0.0)
        principal = abs(payment.amount) - interest - fees
        return max(0.0, principal)
    return 0.0


def _payment_amount(payment: DebtPayment) -> float:
    return payment.amount or 0.0


def _calculate_months_between(start_date: date, end_date: date) -> int:
    return max(0, (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month))


def _month_end(day: date) -> date:
    return day.replace(day=1) + relativedelta(months=1) - relativedelta(days=1)


def _monthly_rate(annual_rate: float) -> float:
    if not annual_rate:
        return 0.0
    return (1 + annual_rate) ** (1 / 12) - 1


def _calculate_debt_balance_from_origin(debt: Debt, end_date: date) -> float:
    if debt.start_date and debt.start_date > end_date:
        return 0.0
    if not debt.original_amount:
        return 0.0

    annual_rate = (debt.interest_rate or 0) / 100
    monthly_rate = _monthly_rate(annual_rate)
    balance = debt.original_amount

    payments = [
        payment for payment in debt.payments
        if payment.payment_date and payment.payment_date >= debt.start_date and payment.payment_date <= end_date
    ]
    payments_by_month = {}
    for payment in payments:
        key = (payment.payment_date.year, payment.payment_date.month)
        payments_by_month.setdefault(key, []).append(payment)

    start_month = debt.start_date.replace(day=1)
    end_month = end_date.replace(day=1)
    current_month = start_month
    end_month_is_complete = end_date == _month_end(end_date)

    while current_month < end_month:
        month_key = (current_month.year, current_month.month)
        if current_month >= start_month:
            balance += balance * monthly_rate
            for payment in payments_by_month.get(month_key, []):
                balance -= _payment_amount(payment)
            balance = max(0.0, balance)
        current_month += relativedelta(months=1)

    if end_month_is_complete:
        month_key = (end_month.year, end_month.month)
        balance += balance * monthly_rate
        for payment in payments_by_month.get(month_key, []):
            balance -= _payment_amount(payment)
    else:
        month_key = (end_month.year, end_month.month)
        for payment in payments_by_month.get(month_key, []):
            if payment.payment_date and payment.payment_date <= end_date:
                balance -= _payment_amount(payment)

    return max(balance, 0.0)


def _calculate_mortgage_balance(debt: Debt, month_end: date, today: date) -> float:
    return _calculate_debt_balance(debt, month_end, today)


def _calculate_debt_balance(debt: Debt, month_end: date, today: date) -> float:
    if debt.start_date and debt.start_date > month_end:
        return 0.0

    if not debt.original_amount:
        return 0.0

    effective_end = min(month_end, today)
    if effective_end >= debt.start_date:
        balance = _calculate_debt_balance_from_origin(debt, effective_end)
    else:
        balance = 0.0

    if month_end <= today:
        return max(balance, 0.0)

    if balance == 0.0 and debt.start_date and debt.start_date > effective_end:
        balance = debt.original_amount

    monthly_payment = debt.monthly_payment or 0.0
    annual_rate = (debt.interest_rate or 0) / 100
    monthly_rate = _monthly_rate(annual_rate)
    current_month_end = _month_end(today)
    months_ahead = _calculate_months_between(current_month_end, month_end)

    for _ in range(months_ahead):
        if monthly_payment <= 0:
            break
        balance += balance * monthly_rate
        balance = max(0.0, balance - monthly_payment)

    return max(balance, 0.0)


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


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _iter_months(start_month: date, end_month: date) -> Iterable[date]:
    current = start_month
    while current <= end_month:
        yield current
        current = current + relativedelta(months=1)


def _month_key(day: date) -> Tuple[int, int]:
    return day.year, day.month


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
    for month_start in _iter_months(start_month, end_month):
        month_end = month_start + relativedelta(months=1) - relativedelta(days=1)
        is_projection = month_start > current_month
        month_entry = {
            "month": month_start.strftime("%Y-%m"),
            "month_name": month_start.strftime("%b %Y"),
            "is_projection": is_projection,
            "debts": {},
            "total_principal_end": 0.0,
        }

        for debt in debts:
            if debt.debt_type == "credit_card":
                continue
            if debt.start_date and month_end < debt.start_date:
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
            annual_rate = _annual_rate_decimal(debt)
            interest_accrued = principal_start * (annual_rate / 12) if annual_rate else 0.0

            if is_projection and include_projection:
                payment_applied = debt.monthly_payment or inferred_payments.get(debt.id, 0.0)
                interest_paid = min(interest_accrued, payment_applied) if payment_applied else 0.0
                principal_paid = max(0.0, payment_applied - interest_paid)
            else:
                month_key = _month_key(month_start)
                payment_data = payment_lookup.get(debt.id, {}).get(month_key, {})
                payment_applied = payment_data.get("amount", 0.0)
                explicit_principal = payment_data.get("principal", 0.0)
                if explicit_principal > 0:
                    principal_paid = min(explicit_principal, principal_start)
                else:
                    interest_paid = min(interest_accrued, payment_applied) if payment_applied else 0.0
                    principal_paid = max(0.0, payment_applied - interest_paid)

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


def _build_mortgage_balance_map(debt: Debt, end_date: date, today: date) -> Optional[dict]:
    if not debt.start_date or debt.original_amount is None or not debt.monthly_payment:
        return None

    annual_rate = (debt.interest_rate or 0) / 100
    monthly_rate = _monthly_rate(annual_rate)

    extra_by_month = {}
    for payment in debt.payments:
        if not payment.payment_date:
            continue
        if payment.payment_date < debt.start_date:
            continue
        if payment.payment_date > end_date:
            continue
        key = (payment.payment_date.year, payment.payment_date.month)
        extra_by_month[key] = extra_by_month.get(key, 0.0) + _payment_principal(payment)

    balance_map = {}
    balance = debt.original_amount or 0.0
    start_month = debt.start_date.replace(day=1)
    end_month = end_date.replace(day=1)
    current_month = start_month
    projection_balance = None

    while current_month <= end_month:
        month_end = current_month + relativedelta(months=1) - relativedelta(days=1)
        month_key = (current_month.year, current_month.month)
        payment_date = _adjust_to_payment_day(current_month, debt.payment_day or debt.start_date.day)

        if month_end < today:
            if month_end >= debt.start_date and payment_date >= debt.start_date:
                interest = balance * monthly_rate
                principal = max(0.0, debt.monthly_payment - interest)
                balance -= principal
            balance -= extra_by_month.get(month_key, 0.0)
            balance = max(0.0, balance)
            balance_map[month_end] = balance
        else:
            if projection_balance is None:
                projection_balance = _calculate_debt_balance_from_origin(debt, today)

            current_month_end = date(today.year, today.month, 1) + relativedelta(months=1) - relativedelta(days=1)

            if month_end == current_month_end:
                balance_map[month_end] = max(0.0, projection_balance)
            else:
                if debt.monthly_payment and projection_balance > 0:
                    interest = projection_balance * monthly_rate
                    principal = max(0.0, debt.monthly_payment - interest)
                    projection_balance -= principal
                projection_balance -= extra_by_month.get(month_key, 0.0)
                projection_balance = max(0.0, projection_balance)
                balance_map[month_end] = projection_balance

        if balance <= 0 and projection_balance is None:
            balance = 0.0

        current_month += relativedelta(months=1)

    return balance_map


def _asset_category(asset: WealthAsset) -> Optional[str]:
    if asset.asset_class in {"inmueble", "activo"}:
        return "bienes"
    if asset.asset_class == "inversion":
        return "inversiones"
    return None


def _asset_value_for_month(
    asset: WealthAsset,
    month_end: date,
    transactions_by_asset: dict[int, list[Transaction]],
    exchange_rate: float
) -> Optional[float]:
    if asset.as_of_date and asset.as_of_date > month_end:
        return None

    if asset.asset_class == "inmueble":
        base_value = apply_expected_appreciation(
            asset.value,
            asset.expected_appreciation_rate,
            asset.as_of_date,
            month_end
        )
    elif asset.asset_class == "activo":
        base_value = apply_depreciation(
            asset.value,
            asset.depreciation_method,
            asset.depreciation_rate,
            asset.depreciation_years,
            asset.depreciation_salvage_value,
            asset.depreciation_start_date or asset.as_of_date,
            month_end
        )
    else:
        base_value = asset.value

    anchor_date = asset.as_of_date or date.min
    transaction_adjustments = 0.0
    for transaction in transactions_by_asset.get(asset.id, []):
        if not transaction.date or transaction.date <= anchor_date:
            continue
        if transaction.date > month_end:
            continue
        movement = -transaction.amount
        transaction_adjustments += convert_to_currency(
            movement,
            transaction.currency_id,
            asset.currency_id,
            exchange_rate
        )

    return max(0.0, (base_value or 0.0) + transaction_adjustments)


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
    start_date_obj, end_date_obj = parse_date_range(start_date, end_date)
    end_date_exclusive = end_date_obj + relativedelta(days=1)

    # Get exchange rate for conversion
    exchange_rate = get_exchange_rate(db)

    # Query ALL transactions (not filtered by currency)
    query = build_spent_transactions_query(
        db,
        start_date_obj,
        end_date_exclusive
    ).with_entities(
        Category.name.label('category_name'),
        CategoryGroup.name.label('group_name'),
        Transaction.amount,
        Transaction.currency_id
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
        'start_date': start_date_obj.isoformat(),
        'end_date': end_date_obj.isoformat(),
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
    start_date_obj, end_date_obj = parse_date_range(start_date, end_date)
    end_date_exclusive = end_date_obj + relativedelta(days=1)

    # Get exchange rate for conversion
    exchange_rate = get_exchange_rate(db)

    # Query ALL transactions (not filtered by currency)
    query = build_spent_transactions_query(
        db,
        start_date_obj,
        end_date_exclusive
    ).with_entities(
        CategoryGroup.name.label('group_name'),
        Transaction.amount,
        Transaction.currency_id
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
        'start_date': start_date_obj.isoformat(),
        'end_date': end_date_obj.isoformat(),
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
        month_end = current_date + relativedelta(months=1)

        # Income (positive amounts) - ALL currencies
        income_transactions = db.query(
            Transaction.amount,
            Transaction.currency_id
        ).join(
            Category, Transaction.category_id == Category.id
        ).join(
            CategoryGroup, Category.category_group_id == CategoryGroup.id
        ).filter(
            and_(
                Transaction.date >= month_start,
                Transaction.date < month_end,
                Transaction.amount > 0,
                Transaction.transfer_account_id.is_(None),
                CategoryGroup.is_income.is_(True)
            )
        ).all()

        income = sum(
            convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
            for t in income_transactions
        )

        # Expenses (negative amounts) - ALL currencies
        expense_transactions = build_spent_transactions_query(
            db,
            month_start,
            month_end
        ).with_entities(
            Transaction.amount,
            Transaction.currency_id
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
        month_end = current_date + relativedelta(months=1)

        income_transactions = db.query(
            Transaction.amount,
            Transaction.currency_id
        ).join(
            Category, Transaction.category_id == Category.id
        ).join(
            CategoryGroup, Category.category_group_id == CategoryGroup.id
        ).filter(
            and_(
                Transaction.date >= month_start,
                Transaction.date < month_end,
                Transaction.amount > 0,
                Transaction.transfer_account_id.is_(None),
                CategoryGroup.is_income.is_(True)
            )
        ).all()

        income = sum(
            convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
            for t in income_transactions
        )

        expense_transactions = build_spent_transactions_query(
            db,
            month_start,
            month_end
        ).with_entities(
            Transaction.amount,
            Transaction.currency_id
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


@router.get("/top-income-expenses")
def get_top_income_expenses(
    months: int = 12,
    currency_id: int = 1,
    limit: int = 5,
    db: Session = Depends(get_db)
):
    """
    Get top income and expense categories for the last N months.
    Transfers are excluded from income and expenses.
    """
    end_date = date.today()
    start_date = end_date - relativedelta(months=months)
    min_start_date = date(2026, 1, 1)
    note = None
    if start_date < min_start_date:
        start_date = min_start_date
        note = 'Los datos anteriores a enero de 2026 no se pueden mostrar porque no se tiene registro.'

    exchange_rate = get_exchange_rate(db)

    income_rows = db.query(
        Transaction.amount,
        Transaction.currency_id,
        Category.name.label('category_name')
    ).join(
        Category, Transaction.category_id == Category.id
    ).join(
        CategoryGroup, Category.category_group_id == CategoryGroup.id
    ).filter(
        and_(
            Transaction.date >= start_date,
            Transaction.date <= end_date,
            Transaction.amount > 0,
            Transaction.transfer_account_id.is_(None),
            CategoryGroup.is_income.is_(True)
        )
    ).all()

    income_totals = {}
    for row in income_rows:
        category_name = row.category_name or 'Sin categoría'
        converted_amount = convert_to_currency(
            row.amount,
            row.currency_id,
            currency_id,
            exchange_rate
        )
        income_totals[category_name] = income_totals.get(category_name, 0) + converted_amount

    income_results = [
        {'category': category_name, 'amount': total}
        for category_name, total in income_totals.items()
    ]
    income_results.sort(key=lambda item: item['amount'], reverse=True)

    end_date_exclusive = end_date + relativedelta(days=1)
    expense_rows = build_spent_transactions_query(
        db,
        start_date,
        end_date_exclusive
    ).with_entities(
        Transaction.amount,
        Transaction.currency_id,
        Category.name.label('category_name')
    ).all()

    expense_totals = {}
    for row in expense_rows:
        category_name = row.category_name or 'Sin categoría'
        converted_amount = convert_to_currency(
            abs(row.amount),
            row.currency_id,
            currency_id,
            exchange_rate
        )
        expense_totals[category_name] = expense_totals.get(category_name, 0) + converted_amount

    expense_results = [
        {'category': category_name, 'amount': total}
        for category_name, total in expense_totals.items()
    ]
    expense_results.sort(key=lambda item: item['amount'], reverse=True)

    return {
        'period': f'{start_date.strftime("%b %Y")} - {end_date.strftime("%b %Y")}',
        'note': note,
        'income': income_results[:limit],
        'expenses': expense_results[:limit]
    }


@router.get("/debt-balance-history")
def get_debt_balance_history(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    projection_months: int = 0,
    include_full_history: bool = False,
    currency_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    Get total debt balance over time using debt payments history.
    """
    debts = db.query(Debt).all()
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

    exchange_rate = get_exchange_rate(db)
    currencies = db.query(Currency).all()
    currency_map = {currency.code: currency.id for currency in currencies}

    monthly_totals = []
    debt_types = sorted({debt.debt_type or 'Sin tipo' for debt in debts})
    current_date = start_date_obj

    while current_date <= end_date_obj:
        month_end = current_date + relativedelta(months=1)
        total_debt = 0.0
        debt_by_type = {debt_type: 0.0 for debt_type in debt_types}

        for debt in debts:
            balance = _calculate_debt_balance(debt, month_end, today)
            debt_currency_id = currency_map.get(debt.currency_code, currency_id)
            converted_balance = convert_to_currency(
                balance,
                debt_currency_id,
                currency_id,
                exchange_rate
            )
            total_debt += converted_balance
            debt_type = debt.debt_type or 'Sin tipo'
            debt_by_type[debt_type] = debt_by_type.get(debt_type, 0.0) + converted_balance

        monthly_totals.append({
            'month': current_date.strftime('%Y-%m'),
            'month_name': current_date.strftime('%b %Y'),
            'total_debt': round(total_debt, 2),
            'debt_by_type': {key: round(value, 2) for key, value in debt_by_type.items()}
        })

        current_date += relativedelta(months=1)

    currency = db.query(Currency).get(currency_id)

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
    """
    Get monthly principal timeline for non-revolving debts (loans/mortgages).
    """
    debts = db.query(Debt).filter(Debt.debt_type != "credit_card").all()
    if not debts:
        return {
            "monthly": [],
            "debts": [],
            "currency": None,
            "current_total_principal": 0,
        }

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
        start_month,
        end_month,
        debts,
        include_projection=include_projection,
        currency_id=currency_id,
        exchange_rate=exchange_rate,
        currency_map=currency_map,
        today=today,
    )

    currency = db.query(Currency).get(currency_id)
    debt_meta = [
        {
            "id": debt.id,
            "name": debt.name,
            "debt_type": debt.debt_type,
            "currency_code": debt.currency_code,
        }
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
        month_end = current_date + relativedelta(months=1)

        # Build query for ALL currencies
        query = build_spent_transactions_query(
            db,
            month_start,
            month_end
        ).with_entities(
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
    month_end = today + relativedelta(days=1)

    # Get exchange rate for conversion
    exchange_rate = get_exchange_rate(db)

    # Current month income - ALL currencies
    income_transactions = db.query(
        Transaction.amount,
        Transaction.currency_id
    ).join(
        Category, Transaction.category_id == Category.id
    ).join(
        CategoryGroup, Category.category_group_id == CategoryGroup.id
    ).filter(
        and_(
            Transaction.date >= month_start,
            Transaction.date <= today,
            Transaction.amount > 0,
            Transaction.transfer_account_id.is_(None),
            CategoryGroup.is_income.is_(True)
        )
    ).all()

    month_income = sum(
        convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
        for t in income_transactions
    )

    # Current month expenses - ALL currencies
    expense_transactions = build_spent_transactions_query(
        db,
        month_start,
        month_end
    ).with_entities(
        Transaction.amount,
        Transaction.currency_id
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
    end_date_exclusive = end_date_obj + relativedelta(days=1)

    income_transactions = db.query(
        Transaction.amount,
        Transaction.currency_id
    ).join(
        Category, Transaction.category_id == Category.id
    ).join(
        CategoryGroup, Category.category_group_id == CategoryGroup.id
    ).filter(
        and_(
            Transaction.date >= start_date_obj,
            Transaction.date <= end_date_obj,
            Transaction.amount > 0,
            Transaction.transfer_account_id.is_(None),
            CategoryGroup.is_income.is_(True)
        )
    ).all()

    expense_transactions = build_spent_transactions_query(
        db,
        start_date_obj,
        end_date_exclusive
    ).with_entities(
        Transaction.amount,
        Transaction.currency_id
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
        month_end = current_date + relativedelta(months=1)

        # Income (excludes transfers)
        income_transactions = db.query(
            Transaction.amount,
            Transaction.currency_id
        ).join(
            Category, Transaction.category_id == Category.id
        ).join(
            CategoryGroup, Category.category_group_id == CategoryGroup.id
        ).filter(
            and_(
                Transaction.date >= month_start,
                Transaction.date < month_end,
                Transaction.amount > 0,
                Transaction.transfer_account_id.is_(None),
                CategoryGroup.is_income.is_(True)
            )
        ).all()

        income = sum(
            convert_to_currency(t.amount, t.currency_id, currency_id, exchange_rate)
            for t in income_transactions
        )

        # Expenses (excludes transfers)
        expense_transactions = build_spent_transactions_query(
            db,
            month_start,
            month_end
        ).with_entities(
            Transaction.amount,
            Transaction.currency_id
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
        month_end = month_start + relativedelta(months=1)

        actual_transactions = build_spent_transactions_query(
            db,
            month_start,
            month_end,
            category_id=category_id
        ).with_entities(
            Transaction.amount,
            Transaction.currency_id
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
    Assets: wealth assets (material assets, real estate, investments)
    Liabilities: active debts (principal only)
    """
    # Default to January 2026 if not specified
    if not start_date:
        start_date = '2026-01-01'
    if not end_date:
        end_date = date.today().isoformat()

    start_date_obj = date.fromisoformat(start_date)
    end_date_obj = date.fromisoformat(end_date)

    exchange_rate = get_exchange_rate(db)

    wealth_assets = db.query(WealthAsset).all()
    debts = db.query(Debt).all()

    assets_by_id = {asset.id: asset for asset in wealth_assets}
    asset_transactions = db.query(Transaction).filter(
        Transaction.investment_asset_id.in_(assets_by_id.keys())
    ).all() if assets_by_id else []
    transactions_by_asset: dict[int, list[Transaction]] = {}
    for transaction in asset_transactions:
        if transaction.investment_asset_id is None:
            continue
        transactions_by_asset.setdefault(transaction.investment_asset_id, []).append(transaction)

    currencies = db.query(Currency).all()
    currency_map = {currency.code: currency.id for currency in currencies}

    monthly_net_worth = []
    current_date = start_date_obj.replace(day=1)
    today = date.today()

    while current_date <= end_date_obj:
        month_start = current_date
        month_end = current_date + relativedelta(months=1) - relativedelta(days=1)

        assets = 0.0
        liabilities = 0.0

        totals_by_category = {"bienes": 0.0, "inversiones": 0.0}
        for asset in wealth_assets:
            category = _asset_category(asset)
            if category is None:
                continue
            asset_value = _asset_value_for_month(
                asset,
                month_end,
                transactions_by_asset,
                exchange_rate
            )
            if asset_value is None:
                continue
            converted_value = convert_to_currency(
                asset_value,
                asset.currency_id,
                currency_id,
                exchange_rate
            )
            totals_by_category[category] += converted_value

        assets = sum(totals_by_category.values())
        for debt in debts:
            balance = _calculate_debt_balance(debt, month_end, today)
            debt_currency_id = currency_map.get(debt.currency_code, currency_id)
            liabilities += convert_to_currency(
                balance,
                debt_currency_id,
                currency_id,
                exchange_rate
            )

        net_worth = assets - liabilities

        monthly_net_worth.append({
            'month': current_date.strftime('%Y-%m'),
            'month_name': current_date.strftime('%b %Y'),
            'assets': round(assets, 2),
            'assets_by_category': {
                'bienes': round(totals_by_category['bienes'], 2),
                'inversiones': round(totals_by_category['inversiones'], 2)
            },
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

    totals_by_category = {"bienes": 0.0, "inversiones": 0.0}
    if monthly_net_worth:
        latest_assets = monthly_net_worth[-1].get('assets_by_category', {})
        totals_by_category['bienes'] = latest_assets.get('bienes', 0.0)
        totals_by_category['inversiones'] = latest_assets.get('inversiones', 0.0)

    return {
        'start_date': start_date_obj.isoformat(),
        'end_date': end_date_obj.isoformat(),
        'monthly': monthly_net_worth,
        'change': round(change, 2),
        'change_percentage': round(change_percentage, 2),
        'current_net_worth': monthly_net_worth[-1]['net_worth'] if monthly_net_worth else 0,
        'totals_by_category': {
            'bienes': round(totals_by_category['bienes'], 2),
            'inversiones': round(totals_by_category['inversiones'], 2)
        },
        'currency': currency.to_dict() if currency else None
    }


@router.get("/real-estate-wealth")
def get_real_estate_wealth(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    projection_months: int = Query(12, ge=0, le=36),
    currency_id: int = 1,
    db: Session = Depends(get_db),
):
    today = date.today()
    if not end_date:
        end_date = today.isoformat()
    if not start_date:
        start_date = (today.replace(day=1) - relativedelta(months=11)).isoformat()

    start_date_obj = date.fromisoformat(start_date)
    end_date_obj = date.fromisoformat(end_date)

    if start_date_obj > end_date_obj:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    try:
        return build_real_estate_wealth_timeline(
            db=db,
            start_date=start_date_obj,
            end_date=end_date_obj,
            projection_months=projection_months,
            currency_id=currency_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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

    for debt in debts:
        debt_currency_id = currency_map.get(debt.currency_code, currency_id)
        current_balance_raw = _calculate_debt_balance(debt, today, today)
        projected_balance_raw = _calculate_debt_balance(debt, projection_end, today)
        original_amount_raw = debt.original_amount or 0

        # Convert amounts to selected currency
        current_balance = convert_to_currency(
            current_balance_raw,
            debt_currency_id,
            currency_id,
            exchange_rate
        )

        monthly_payment = convert_to_currency(
            debt.monthly_payment or 0,
            debt_currency_id,
            currency_id,
            exchange_rate
        )
        original_amount = convert_to_currency(
            original_amount_raw,
            debt_currency_id,
            currency_id,
            exchange_rate
        )
        projected_balance = convert_to_currency(
            projected_balance_raw,
            debt_currency_id,
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
                debt_currency_id,
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

    # Sort by balance descending
    debt_details.sort(key=lambda x: x['current_balance'], reverse=True)

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
