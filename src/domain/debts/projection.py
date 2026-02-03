from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from domain.debts.repository import (
    fetch_currency_codes,
    fetch_debt_category_allocations,
    fetch_recurring_expense_transactions,
)
from domain.debts.service import get_debts_principal
from domain.debts.types import DebtPrincipalRecord
from domain.fx.service import convert_from_cop, convert_to_cop
from finance_app.models import Debt
from finance_app.services.recurring_service import get_next_occurrence_date, get_next_scheduled_date


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _iter_months(start_month: date, end_month: date) -> Iterable[date]:
    current = _month_start(start_month)
    end_month = _month_start(end_month)
    while current <= end_month:
        yield current
        current = current + relativedelta(months=1)


def _scheduled_occurrences(
    db: Session,
    start_date: date,
    end_date: date,
) -> List[dict]:
    recurring_items = fetch_recurring_expense_transactions(db)
    currency_codes = fetch_currency_codes(db)
    occurrences: List[dict] = []

    for recurring in recurring_items:
        if not recurring.category_id:
            continue
        if recurring.transaction_type == "income":
            continue

        next_date = get_next_scheduled_date(recurring)
        if not next_date:
            continue

        while next_date < end_date:
            if next_date >= start_date:
                occurrences.append({
                    "date": next_date,
                    "category_id": recurring.category_id,
                    "amount": abs(recurring.amount),
                    "currency_code": currency_codes.get(recurring.currency_id, "COP"),
                })
            next_date = get_next_occurrence_date(recurring, next_date)

    return occurrences


def _allocate_payment(
    debts_by_id: Dict[int, DebtPrincipalRecord],
    category_debt_ids: List[int],
    amount_cop: Decimal,
    payment_date: date,
    db: Session,
) -> None:
    if not category_debt_ids or amount_cop <= 0:
        return

    candidates = [debts_by_id[debt_id] for debt_id in category_debt_ids if debt_id in debts_by_id]
    if not candidates:
        return

    principals = {record.debt_id: record.principal_cop for record in candidates}
    max_principal = max(principals.values()) if principals else Decimal("0")
    if max_principal <= 0:
        return

    top_debts = [debt_id for debt_id, principal in principals.items() if principal == max_principal]
    allocations: Dict[int, Decimal] = {}

    if len(top_debts) == 1:
        allocations[top_debts[0]] = amount_cop
    else:
        total_principal = sum(principals.values())
        if total_principal <= 0:
            return
        for debt_id, principal in principals.items():
            allocations[debt_id] = amount_cop * (principal / total_principal)

    for debt_id, allocated_cop in allocations.items():
        record = debts_by_id[debt_id]
        if record.principal_cop <= 0:
            continue

        reduction_cop = min(record.principal_cop, allocated_cop)
        new_principal_cop = record.principal_cop - reduction_cop

        debt_currency_code = record.currency_code
        reduction_original = convert_from_cop(reduction_cop, debt_currency_code, payment_date, db=db)
        new_principal_original = record.principal_original - reduction_original
        if new_principal_original < 0:
            new_principal_original = Decimal("0")

        debts_by_id[debt_id] = DebtPrincipalRecord(
            as_of_date=record.as_of_date,
            debt_id=record.debt_id,
            debt_name=record.debt_name,
            currency_code=record.currency_code,
            principal_original=new_principal_original,
            principal_cop=new_principal_cop,
            status=record.status,
            debt_type=record.debt_type,
        )


def _resolve_category_debts(
    debts: List[Debt],
    allocation_map: Dict[int, List[int]],
    category_id: int,
) -> List[int]:
    if category_id in allocation_map:
        return allocation_map[category_id]

    return [debt.id for debt in debts if debt.category_id == category_id]


def project_debt_principal(
    db: Session,
    start_month: date,
    end_month: date,
) -> List[dict]:
    debts = db.query(Debt).all()
    allocation_map = fetch_debt_category_allocations(db)
    timeline: List[dict] = []

    current_records = get_debts_principal(db, _month_start(start_month))
    debts_by_id: Dict[int, DebtPrincipalRecord] = {record.debt_id: record for record in current_records}

    for month_start in _iter_months(start_month, end_month):
        month_end = month_start + relativedelta(months=1)
        month_records = {
            debt_id: DebtPrincipalRecord(
                as_of_date=month_start,
                debt_id=record.debt_id,
                debt_name=record.debt_name,
                currency_code=record.currency_code,
                principal_original=record.principal_original,
                principal_cop=record.principal_cop,
                status=record.status,
                debt_type=record.debt_type,
            )
            for debt_id, record in debts_by_id.items()
        }

        timeline.append({
            "month": month_start.strftime("%Y-%m"),
            "as_of_date": month_start,
            "records": list(month_records.values()),
        })

        occurrences = _scheduled_occurrences(db, month_start, month_end)
        if not occurrences:
            continue

        payments_by_category: Dict[int, List[dict]] = defaultdict(list)
        for occurrence in occurrences:
            payments_by_category[occurrence["category_id"]].append(occurrence)

        for category_id, payments in payments_by_category.items():
            total_cop = sum(
                convert_to_cop(
                    payment["amount"],
                    payment["currency_code"],
                    payment["date"],
                    db=db,
                )
                for payment in payments
            )
            matching_debt_ids = _resolve_category_debts(debts, allocation_map, category_id)
            _allocate_payment(
                debts_by_id,
                matching_debt_ids,
                total_cop,
                payments[0]["date"],
                db,
            )

    return timeline
