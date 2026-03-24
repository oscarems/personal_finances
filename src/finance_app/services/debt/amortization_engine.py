from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, List, Optional, Tuple

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from finance_app.models import Debt, DebtPayment, MortgagePaymentAllocation, Transaction

TWOPLACES = Decimal("0.01")


class UnsupportedAmortizationTypeError(ValueError):
    pass


@dataclass(frozen=True)
class ScheduleEntry:
    period_index: int
    date: date
    opening_balance: float
    interest: float
    principal: float
    payment: float
    extra_payment: float
    ending_balance: float
    is_extra_payment_applied: bool
    is_paid_real: bool

    def to_dict(self) -> dict:
        return {
            "period_index": self.period_index,
            "date": self.date,
            "opening_balance": self.opening_balance,
            "interest": self.interest,
            "principal": self.principal,
            "payment": self.payment,
            "extra_payment": self.extra_payment,
            "ending_balance": self.ending_balance,
            "is_extra_payment_applied": self.is_extra_payment_applied,
            "is_paid_real": self.is_paid_real,
        }


class AmortizationEngine:
    def __init__(self, db: Optional[Session] = None, annual_rate_convention: str = "effective"):
        self.db = db
        self.annual_rate_convention = annual_rate_convention

    @staticmethod
    def _month_start(day: date) -> date:
        return day.replace(day=1)

    @staticmethod
    def _round(value: float) -> float:
        return float(Decimal(str(value)).quantize(TWOPLACES, rounding=ROUND_HALF_UP))

    def _iter_months(self, start_month: date) -> Iterable[date]:
        current = self._month_start(start_month)
        while True:
            yield current
            current = current + relativedelta(months=1)

    def _annual_rate_decimal(self, debt: Debt) -> float:
        if debt.annual_interest_rate is not None:
            value = float(debt.annual_interest_rate)
            return value / 100 if value > 1 else value
        if debt.interest_rate is not None:
            value = float(debt.interest_rate)
            return value / 100 if value > 1 else value
        return 0.0

    def _monthly_rate(self, debt: Debt) -> float:
        note = (debt.notes or "").lower()
        if "tasa_mensual" in note or "monthly_rate" in note:
            if debt.annual_interest_rate is not None:
                value = float(debt.annual_interest_rate)
            elif debt.interest_rate is not None:
                value = float(debt.interest_rate)
            else:
                value = 0.0
            return value / 100 if value > 1 else value

        annual = self._annual_rate_decimal(debt)
        if annual == 0:
            return 0.0
        if self.annual_rate_convention == "nominal":
            return annual / 12
        return (1 + annual) ** (1 / 12) - 1

    def _term_months(self, debt: Debt) -> int:
        if debt.term_months:
            return int(debt.term_months)
        if debt.loan_years:
            return int(debt.loan_years) * 12
        return 0

    def _payment_day(self, debt: Debt) -> int:
        if debt.payment_day:
            return max(1, min(31, int(debt.payment_day)))
        if debt.start_date:
            return debt.start_date.day
        return 1

    def _resolve_amortization_type(self, debt: Debt) -> str:
        note = (debt.notes or "").lower()
        if any(token in note for token in ["capital_fijo", "fixed_principal", "aleman", "alemán"]):
            return "fixed_principal"
        if any(token in note for token in ["solo_interes", "interest_only", "sólo interés", "solo interes"]):
            return "interest_only"
        if any(token in note for token in ["cuota_fija", "fixed_payment", "frances", "francés"]):
            return "fixed_payment"
        if debt.debt_type in {"mortgage", "credit_loan"}:
            return "fixed_payment"
        raise UnsupportedAmortizationTypeError(
            f"Tipo de amortización no soportado para deuda {debt.id}: '{debt.debt_type}'"
        )

    def _planned_payment(self, amortization_type: str, balance: float, monthly_rate: float, term_months: int, monthly_payment: float, base_payment: float = 0.0) -> float:
        if amortization_type == "interest_only":
            return balance * monthly_rate
        if base_payment and base_payment > 0:
            return base_payment
        if monthly_payment and monthly_payment > 0:
            return monthly_payment
        if term_months <= 0:
            return balance
        if amortization_type == "fixed_principal":
            return (balance / term_months) + (balance * monthly_rate)
        if monthly_rate == 0:
            return balance / term_months
        factor = (1 + monthly_rate) ** term_months
        return balance * (monthly_rate * factor) / (factor - 1)

    def _collect_real_monthly_payments(self, debt: Debt) -> Dict[Tuple[int, int], Dict[str, float]]:
        result: Dict[Tuple[int, int], Dict[str, float]] = {}
        if not self.db:
            return result

        allocations = self.db.query(MortgagePaymentAllocation).filter_by(loan_id=debt.id).all()
        allocation_tx_ids = {item.transaction_id for item in allocations if item.transaction_id}

        for payment in self.db.query(DebtPayment).filter_by(debt_id=debt.id).all():
            if not payment.payment_date:
                continue
            if payment.transaction_id and payment.transaction_id in allocation_tx_ids:
                continue
            k = (payment.payment_date.year, payment.payment_date.month)
            bucket = result.setdefault(k, {"total": 0.0, "principal": 0.0, "interest": 0.0, "real": True})
            total = float(payment.amount or 0.0)
            interest = float(payment.interest or 0.0)
            principal = float(payment.principal) if payment.principal is not None else max(0.0, total - interest - float(payment.fees or 0.0))
            bucket["total"] += total
            bucket["interest"] += max(0.0, interest)
            bucket["principal"] += max(0.0, principal)

        for alloc in allocations:
            if not alloc.payment_date:
                continue
            k = (alloc.payment_date.year, alloc.payment_date.month)
            bucket = result.setdefault(k, {"total": 0.0, "principal": 0.0, "interest": 0.0, "real": True})
            principal = float(alloc.principal_paid or 0.0) + float(alloc.extra_principal_paid or 0.0)
            interest = float(alloc.interest_paid or 0.0)
            total = principal + interest + float(alloc.fees_paid or 0.0) + float(alloc.escrow_paid or 0.0)
            bucket["total"] += total
            bucket["principal"] += principal
            bucket["interest"] += interest

        # Fallback heurístico por transacciones de categoría/cuenta/texto.
        # Requires matching category + account AND at least one keyword
        # in memo (debt name must be 3+ chars to avoid false positives).
        if not result and debt.category_id and self.db:
            debt_name = (debt.name or "").lower().strip()
            kw = ["hipoteca", "mortgage", "cuota", "crédito", "credito"]
            if len(debt_name) >= 3:
                kw.append(debt_name)
            monthly_payment = float(debt.monthly_payment or 0)
            transactions = self.db.query(Transaction).filter(
                Transaction.category_id == debt.category_id,
                Transaction.account_id == debt.account_id,
                Transaction.amount < 0,
            ).all()
            for tx in transactions:
                memo = (tx.memo or "").lower()
                if not any(token in memo for token in kw):
                    continue
                amount = abs(float(tx.amount))
                # Skip transactions that are less than 50% of expected payment
                # (likely unrelated small transactions)
                if monthly_payment > 0 and amount < monthly_payment * 0.5:
                    continue
                k = (tx.date.year, tx.date.month)
                bucket = result.setdefault(k, {"total": 0.0, "principal": 0.0, "interest": 0.0, "real": True})
                bucket["total"] += amount
                bucket["principal"] += amount
        return result

    def generate_schedule(self, debt: Debt, as_of: Optional[date] = None, mode: str = "plan") -> List[dict]:
        if not debt.start_date:
            return []
        amortization_type = self._resolve_amortization_type(debt)
        monthly_rate = self._monthly_rate(debt)
        term_months = self._term_months(debt)
        real_payments = self._collect_real_monthly_payments(debt) if mode in {"actual", "hybrid"} else {}
        balance = float(debt.original_amount or debt.current_balance or 0.0)
        cutoff = as_of or date.today()
        max_periods = max(term_months * 2, 600) if term_months else 600

        base_payment = float(debt.monthly_payment or 0.0)
        if amortization_type == "fixed_payment" and base_payment <= 0:
            base_payment = self._planned_payment(amortization_type, balance, monthly_rate, max(term_months, 1), 0.0)

        rows: List[ScheduleEntry] = []
        for idx, month_start in enumerate(self._iter_months(debt.start_date), start=1):
            if idx > max_periods or balance <= 0:
                break
            opening = balance
            interest = opening * monthly_rate
            key = (month_start.year, month_start.month)
            use_real = mode == "actual" or (mode == "hybrid" and month_start <= self._month_start(cutoff) and key in real_payments)
            planned_payment = self._planned_payment(
                amortization_type,
                opening,
                monthly_rate,
                max(term_months - idx + 1, 1),
                float(debt.monthly_payment or 0.0),
                base_payment=base_payment if amortization_type == "fixed_payment" else 0.0,
            )

            if use_real:
                payment_total = real_payments[key].get("total", 0.0)
                principal_paid = real_payments[key].get("principal", 0.0)
                interest_paid = real_payments[key].get("interest", 0.0)
                if principal_paid <= 0 and payment_total > 0:
                    principal_paid = max(0.0, payment_total - min(interest, payment_total))
                    interest_paid = min(interest, payment_total)
                base_principal = max(0.0, planned_payment - interest)
                extra_payment = max(0.0, principal_paid - base_principal)
                is_paid_real = True
            else:
                payment_total = planned_payment
                if amortization_type == "fixed_principal":
                    base_principal = (float(debt.original_amount or opening) / max(term_months, 1))
                    principal_paid = base_principal
                elif amortization_type == "interest_only":
                    principal_paid = 0.0
                else:
                    principal_paid = max(0.0, planned_payment - interest)
                interest_paid = interest
                extra_payment = 0.0
                is_paid_real = False

            principal_paid = min(opening, principal_paid)
            ending = max(0.0, opening - principal_paid)
            if ending <= 0.01:
                principal_paid += ending
                ending = 0.0
                payment_total = principal_paid + interest_paid

            rows.append(
                ScheduleEntry(
                    period_index=idx,
                    date=month_start,
                    opening_balance=self._round(opening),
                    interest=self._round(interest_paid),
                    principal=self._round(principal_paid),
                    payment=self._round(payment_total),
                    extra_payment=self._round(extra_payment),
                    ending_balance=self._round(ending),
                    is_extra_payment_applied=extra_payment > 0,
                    is_paid_real=is_paid_real,
                )
            )
            balance = ending

            if as_of and mode == "actual" and month_start > self._month_start(as_of):
                break

        return [row.to_dict() for row in rows]

    def balance_as_of(self, debt: Debt, date_value: date, mode: str = "hybrid") -> float:
        schedule = self.generate_schedule(debt, as_of=date_value, mode=mode)
        if not schedule:
            return max(0.0, float(debt.current_balance or 0.0))
        rows = [row for row in schedule if row["date"] <= self._month_start(date_value)]
        if not rows:
            return max(0.0, float(debt.original_amount or debt.current_balance or 0.0))
        return max(0.0, rows[-1]["ending_balance"])
