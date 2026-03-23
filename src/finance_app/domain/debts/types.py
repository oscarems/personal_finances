from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class DebtPrincipalRecord:
    as_of_date: date
    debt_id: int
    debt_name: str
    currency_code: str
    principal_original: Decimal
    principal_cop: Decimal
    status: str
    debt_type: str
