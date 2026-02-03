from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List

from sqlalchemy.orm import Session

from domain.debts.repository import fetch_debts
from domain.debts.types import DebtPrincipalRecord
from domain.fx.service import convert_to_cop
from finance_app.services.debt_balance_service import calculate_debt_balance_as_of


def _decimalize(value: float | int | Decimal | None) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def get_debts_principal(db: Session, as_of_date: date) -> List[DebtPrincipalRecord]:
    debts = fetch_debts(db, include_inactive=True)
    records: List[DebtPrincipalRecord] = []

    for debt in debts:
        if debt.debt_type == "mortgage":
            principal_value = calculate_debt_balance_as_of(
                db=db,
                debt=debt,
                as_of_date=as_of_date,
                today=as_of_date,
                include_projection=False,
            )
        else:
            principal_value = debt.current_balance or 0.0

        principal_original = _decimalize(principal_value)
        principal_cop = convert_to_cop(principal_original, debt.currency_code, as_of_date, db=db)
        status = "open" if debt.is_active and principal_original > 0 else "closed"

        records.append(
            DebtPrincipalRecord(
                as_of_date=as_of_date,
                debt_id=debt.id,
                debt_name=debt.name,
                currency_code=debt.currency_code,
                principal_original=principal_original,
                principal_cop=principal_cop,
                status=status,
                debt_type=debt.debt_type,
            )
        )

    return records


def get_total_debt_principal_cop(db: Session, as_of_date: date) -> Decimal:
    records = get_debts_principal(db, as_of_date)
    return sum(
        (record.principal_cop for record in records if record.status == "open"),
        Decimal("0"),
    )
