"""
Debt calculation helpers -- extracted from api/debts.py.
Pure business logic, no HTTP/FastAPI dependencies.
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from finance_app.models import (
    Debt,
    DebtAmortizationMonthly,
    DebtPayment,
)

from finance_app.services.debt.balance_service import (
    calculate_scheduled_principal_balance,
)
from finance_app.services.debt.amortization_service import (
    ensure_debt_amortization_records,
    fetch_amortization_for_month,
)


def normalize_rate_units(rate: float) -> float:
    """Normalise a stored rate to decimal form.

    Convention used across debt helpers, simulator and amortization engine:
    values **> 1** are treated as a percentage (e.g. ``1.9`` → ``0.019`` = 1.9%/mo);
    values **≤ 1** are already decimal (e.g. ``0.019``).
    """
    return rate / 100 if rate > 1 else rate


def effective_monthly_interest_rate(debt: Debt) -> float:
    """Effective monthly interest rate as a decimal (e.g. 0.019 for 1.9%/mo).

    Priority matches CLAUDE.md / AmortizationEngine:
    1) ``monthly_interest_rate`` — percent if > 1, else already decimal
       (``normalize_rate_units``).
    2) ``annual_interest_rate`` then ``interest_rate`` (same percent/decimal heuristic),
       converted with effective annual: ``(1 + annual)^(1/12) - 1``.

    Rate unit convention: values > 1 are percentages; ≤ 1 are decimals.
    Callers (simulator, cost analysis, CC helpers) must use this function — do not
    hard-code ``rate / 100``.
    """
    if getattr(debt, "monthly_interest_rate", None):
        return normalize_rate_units(float(debt.monthly_interest_rate))

    annual_rate_raw = debt.annual_interest_rate or debt.interest_rate
    if not annual_rate_raw:
        return 0.0

    annual_decimal = normalize_rate_units(float(annual_rate_raw))
    return (1 + annual_decimal) ** (1 / 12) - 1


def calculate_credit_card_monthly_interest(
    debt: Debt,
    db: Session | None = None,
    *,
    balance: float | None = None,
) -> float:
    """Estimate the monthly interest charge on a credit card balance.

    Uses the effective annual rate convention: monthly = (1 + annual)^(1/12) - 1.
    Falls back to nominal (annual / 12) when annual_interest_rate is not set.

    Args:
        debt: Debt model instance with debt_type == 'credit_card'.
        db: Optional session for FX when account currency ≠ debt currency.
        balance: Optional override (e.g. mid-projection declining balance).
            When omitted, credit cards use the FX-derived account balance;
            other debt types use ``debt.current_balance``.

    Returns:
        Estimated interest amount for the current month (always >= 0).
    """
    bal = float(balance) if balance is not None else _balance_for_payment_calcs(debt, db)
    if bal <= 0:
        return 0.0

    monthly_rate = effective_monthly_interest_rate(debt)
    if monthly_rate <= 0:
        return 0.0
    return round(bal * monthly_rate, 2)


def calculate_suggested_minimum_payment(
    debt: Debt,
    db: Session | None = None,
    *,
    balance: float | None = None,
) -> float:
    """Calculate the suggested minimum payment for a credit card.

    Formula (standard): max(stored minimum, monthly_interest + 1% of balance).
    This ensures the payment at least covers interest plus a small principal chunk.
    If both interest rate and balance are unknown, returns the stored minimum.

    Args:
        debt: Debt model instance with debt_type == 'credit_card'.
        db: Optional session for FX when account currency ≠ debt currency.
        balance: Optional override for declining-balance projections.

    Returns:
        Suggested minimum payment (always >= 0).
    """
    stored_min = float(debt.minimum_payment or 0.0)
    bal = float(balance) if balance is not None else _balance_for_payment_calcs(debt, db)
    if bal <= 0:
        return 0.0

    monthly_interest = calculate_credit_card_monthly_interest(debt, db, balance=bal)
    # 1% of balance covers a token principal reduction
    principal_chunk = bal * 0.01
    calculated = monthly_interest + principal_chunk

    # If min_payment_percentage is set, it acts as an additional floor
    if getattr(debt, "min_payment_percentage", None):
        pct_minimum = bal * (float(debt.min_payment_percentage) / 100)
        calculated = max(calculated, pct_minimum)

    return round(max(stored_min, calculated), 2)


def _balance_for_payment_calcs(debt: Debt, db: Session | None = None) -> float:
    """Balance used for interest / minimum suggestions.

    Credit cards: FX-converted account-derived balance.
    Other debts: stored ``current_balance``.
    """
    if getattr(debt, "debt_type", None) == "credit_card":
        return get_credit_card_current_balance(debt, db)
    return float(debt.current_balance or 0.0)


def get_billing_cycle_info(debt: Debt, reference_date: date | None = None) -> dict:
    """Calculate the current billing cycle for a credit card.

    Returns a dict with statement and payment due dates relative to
    ``reference_date`` (defaults to today).

    Keys returned:
        statement_day, payment_due_day,
        current_cycle_start, current_cycle_end,
        payment_due_date,
        days_until_statement, days_until_payment_due
    All date values are ISO-format strings or None.
    """
    statement_day = getattr(debt, "statement_day", None)
    payment_due_day = getattr(debt, "payment_due_day", None)

    empty: dict = {
        "statement_day": statement_day,
        "payment_due_day": payment_due_day,
        "current_cycle_start": None,
        "current_cycle_end": None,
        "payment_due_date": None,
        "days_until_statement": None,
        "days_until_payment_due": None,
    }

    if not statement_day:
        return empty

    ref = reference_date or date.today()
    stmt_day = int(statement_day)

    def _safe_date(year: int, month: int, day: int) -> date:
        """Clamp day to the last valid day of the month."""
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, min(day, last_day))

    # Determine current cycle end (next statement close)
    if ref.day < stmt_day:
        cycle_end = _safe_date(ref.year, ref.month, stmt_day)
    else:
        # Move to next month
        if ref.month == 12:
            cycle_end = _safe_date(ref.year + 1, 1, stmt_day)
        else:
            cycle_end = _safe_date(ref.year, ref.month + 1, stmt_day)

    # Cycle start is one month before cycle_end + 1 day
    from dateutil.relativedelta import relativedelta as _rd
    cycle_start = cycle_end - _rd(months=1) + _rd(days=1)

    # Payment due date: payment_due_day of the month after cycle_end
    payment_due_date = None
    days_until_payment_due = None
    if payment_due_day:
        due_month = cycle_end.month + 1
        due_year = cycle_end.year
        if due_month > 12:
            due_month = 1
            due_year += 1
        payment_due_date = _safe_date(due_year, due_month, int(payment_due_day))
        days_until_payment_due = (payment_due_date - ref).days

    return {
        "statement_day": stmt_day,
        "payment_due_day": int(payment_due_day) if payment_due_day else None,
        "current_cycle_start": cycle_start.isoformat(),
        "current_cycle_end": cycle_end.isoformat(),
        "payment_due_date": payment_due_date.isoformat() if payment_due_date else None,
        "days_until_statement": (cycle_end - ref).days,
        "days_until_payment_due": days_until_payment_due,
    }


def payment_principal_amount(payment: DebtPayment) -> float:
    """Extract the principal portion from a debt payment.

    Falls back to ``amount - interest - fees`` when ``principal`` is not set.

    Args:
        payment: Debt payment record.

    Returns:
        Principal amount (always >= 0).
    """
    if payment.principal is not None:
        return max(0.0, payment.principal)
    if payment.amount is None:
        return 0.0
    interest = payment.interest or 0.0
    fees = payment.fees or 0.0
    principal = payment.amount - interest - fees
    return max(0.0, principal)


def calculate_principal_from_components(
    amount: float,
    principal: float | None = None,
    interest: float | None = None,
    fees: float | None = None,
) -> float:
    """Derive the principal from explicit components or by subtraction.

    Args:
        amount: Total payment amount.
        principal: Explicit principal, if provided.
        interest: Interest portion.
        fees: Fee portion.

    Returns:
        Principal amount (always >= 0).
    """
    if principal is not None:
        return max(0.0, principal)
    interest = interest or 0.0
    fees = fees or 0.0
    return max(0.0, amount - interest - fees)


def calculate_loan_current_balance(debt: Debt, db: Session) -> float:
    """Return the current balance for a mortgage or credit_loan debt.

    Uses the scheduled amortization plan to calculate the balance as of today.

    Args:
        debt: Debt model instance.
        db: Database session.

    Returns:
        Current balance.  Falls back to ``debt.current_balance`` for
        unsupported debt types.
    """
    if debt.debt_type not in {"mortgage", "credit_loan"}:
        return debt.current_balance
    return calculate_scheduled_principal_balance(debt=debt, as_of_date=date.today())


def payment_source_label(transaction_id: int | None) -> str:
    """Return a human-readable label for the payment source.

    Args:
        transaction_id: Transaction ID linked to the payment, or None.

    Returns:
        ``'transaccion'`` if linked, ``'presupuesto'`` otherwise.
    """
    return "transaccion" if transaction_id else "presupuesto"


def get_credit_card_current_balance(
    debt: Debt,
    db: Session | None = None,
) -> float:
    """Derive credit-card debt balance from the linked account balance.

    Credit cards show the negative account balance as positive debt.
    When the account currency differs from ``debt.currency_code``, the balance
    is converted via ``exchange_rate_service.convert_currency`` (same path as
    transaction updates in ``_cc_balance_in_debt_currency``).

    Args:
        debt: Debt model instance with ``debt_type == 'credit_card'``.
        db: Optional session used for FX lookup. If omitted and conversion is
            needed, a short-lived ``SessionLocal`` is opened.

    Returns:
        Current credit-card balance in ``debt.currency_code`` (always >= 0).
    """
    account = debt.account
    account_balance = account.balance if account else 0.0
    raw_balance = max(0.0, -(account_balance or 0.0))
    if raw_balance <= 0:
        return 0.0

    debt_code = (debt.currency_code or "COP").upper()
    acct_code = _account_currency_code(account, db)
    if acct_code == debt_code:
        return raw_balance

    owns_session = False
    session = db
    if session is None:
        from finance_app.database import SessionLocal

        session = SessionLocal()
        owns_session = True
    try:
        from finance_app.services.exchange_rate_service import convert_currency

        return float(convert_currency(raw_balance, acct_code, debt_code, session))
    finally:
        if owns_session:
            session.close()


def _account_currency_code(account, db: Session | None = None) -> str:
    """Resolve the ISO currency code for an account (default COP)."""
    if account is None:
        return "COP"
    currency = getattr(account, "currency", None)
    if currency is not None and getattr(currency, "code", None):
        return str(currency.code).upper()
    currency_id = getattr(account, "currency_id", None)
    if currency_id is not None and db is not None:
        from finance_app.models import Currency

        row = db.query(Currency).filter_by(id=currency_id).first()
        if row and row.code:
            return str(row.code).upper()
    return "COP"


def _build_debt_payment_entries(debt: Debt, db: Session) -> list[dict]:
    """Collect DebtPayment records for a mortgage or credit_loan debt.

    Args:
        debt: Debt model instance.
        db: Database session.

    Returns:
        List of payment entry dicts.
    """
    debt_payments = db.query(DebtPayment).filter_by(debt_id=debt.id).order_by(
        DebtPayment.payment_date.asc(),
        DebtPayment.id.asc()
    ).all()

    payments: list[dict] = []

    for payment in debt_payments:
        principal = payment_principal_amount(payment)
        payments.append({
            "id": payment.id,
            "debt_id": payment.debt_id,
            "transaction_id": payment.transaction_id,
            "payment_date": payment.payment_date.isoformat() if payment.payment_date else None,
            "amount": payment.amount,
            "principal": principal,
            "interest": payment.interest,
            "fees": payment.fees or 0.0,
            "balance_after": None,
            "notes": payment.notes,
            "payment_source": payment_source_label(payment.transaction_id),
        })

    return payments


def _apply_running_balance(payments: list[dict], original_amount: float) -> list[dict]:
    """Sort payments chronologically and compute running balance_after.

    Also adds Spanish alias fields expected by the UI.

    Args:
        payments: List of payment entry dicts (mutated in place).
        original_amount: Starting debt balance.

    Returns:
        The sorted payments list with balance_after populated.
    """
    payments.sort(key=lambda entry: (date.fromisoformat(entry["payment_date"]), entry["id"] or 0))

    balance = original_amount
    for entry in payments:
        principal = entry.get("principal") or 0.0
        balance = max(0.0, balance - principal)
        entry["balance_after"] = balance
        entry["fecha"] = entry["payment_date"]
        entry["monto_total_pagado"] = entry["amount"]
        entry["monto_principal"] = entry["principal"]
        entry["monto_interes"] = entry["interest"]
        entry["saldo_restante_despues_del_pago"] = entry["balance_after"]
        entry["fuente_del_pago"] = entry["payment_source"]

    return payments


def build_mortgage_payment_history(debt: Debt, db: Session) -> list[dict]:
    """Build a chronologically sorted payment history for a mortgage or credit_loan.

    Mortgages no longer track real-payment allocations — this is purely the
    recorded DebtPayment entries (informational; they do not affect the
    mortgage's derived balance) with a running balance computed for display.

    Works for both ``mortgage`` and ``credit_loan`` debt types.

    Args:
        debt: Debt model instance.
        db: Database session.

    Returns:
        List of payment dicts with running ``balance_after``.
    """
    payments = _build_debt_payment_entries(debt, db)
    if not payments:
        return []

    original_balance = debt.original_amount if debt.original_amount is not None else (debt.current_balance or 0.0)
    return _apply_running_balance(payments, original_balance)


# Alias for clarity — works for both mortgage and credit_loan.
build_loan_payment_history = build_mortgage_payment_history


def debt_to_dict_with_calculated_balance(
    debt: Debt,
    db: Session,
    include_payments: bool = False,
    amortization_map: dict[int, DebtAmortizationMonthly] | None = None,
) -> dict:
    """Serialize a Debt to a dict with a freshly calculated ``current_balance``.

    For credit cards, the balance is derived from the linked account.
    For loans, the amortization records or scheduled balance is used.

    Args:
        debt: Debt model instance.
        db: Database session.
        include_payments: Whether to include payment history in the output.
        amortization_map: Pre-fetched amortization records keyed by debt_id.

    Returns:
        Dict representation of the debt with ``current_balance`` and
        ``paid_percentage`` fields.
    """
    data = debt.to_dict(include_payments=include_payments)
    if debt.debt_type == "credit_card":
        data["current_balance"] = get_credit_card_current_balance(debt, db)
        if debt.original_amount and debt.original_amount > 0:
            data["paid_percentage"] = ((debt.original_amount - data["current_balance"]) / debt.original_amount) * 100
        # Credit-card specific enrichment: interest estimate + suggested minimum payment
        data["monthly_interest_estimate"] = calculate_credit_card_monthly_interest(debt, db)
        data["suggested_minimum_payment"] = calculate_suggested_minimum_payment(debt, db)
        # Recompute utilization from FX-converted balance (to_dict used stored balance).
        effective_limit = data.get("effective_credit_limit")
        if effective_limit and effective_limit > 0:
            data["utilization_percentage"] = (data["current_balance"] / float(effective_limit)) * 100
        else:
            data["utilization_percentage"] = None
        # Utilization thresholds for UI alerts
        util = data.get("utilization_percentage")
        if util is not None:
            if util >= 70:
                data["utilization_alert"] = "critical"
            elif util >= 30:
                data["utilization_alert"] = "warning"
            else:
                data["utilization_alert"] = "ok"
        else:
            data["utilization_alert"] = "unknown"
        # Reconciliation discrepancy for credit cards
        if debt.confirmed_balance is not None:
            data["balance_discrepancy"] = round(float(debt.confirmed_balance) - data["current_balance"], 2)
        else:
            data["balance_discrepancy"] = None
        return data

    today = date.today()
    current_month = today.replace(day=1)
    current_record = None
    if amortization_map is not None:
        current_record = amortization_map.get(debt.id)
    else:
        ensure_debt_amortization_records(db, current_month, current_month)
        amortization_map = fetch_amortization_for_month(db, current_month, [debt.id])
        current_record = amortization_map.get(debt.id)
    if debt.debt_type in {"mortgage", "credit_loan"}:
        calculated_balance = calculate_loan_current_balance(debt, db)
    elif current_record:
        calculated_balance = current_record.principal_remaining
    else:
        calculated_balance = debt.current_balance or 0.0
    data["current_balance"] = calculated_balance
    if debt.original_amount and debt.original_amount > 0:
        data["paid_percentage"] = ((debt.original_amount - calculated_balance) / debt.original_amount) * 100

    # Reconciliation: compare confirmed balance (from bank statement) with calculated.
    # Mortgages are fully derived from original_amount/start_date/rate/term, so
    # manual balance confirmation no longer applies to them.
    if debt.debt_type != "mortgage" and debt.confirmed_balance is not None:
        confirmed = float(debt.confirmed_balance)
        data["balance_discrepancy"] = round(confirmed - float(calculated_balance), 2)
    else:
        data["balance_discrepancy"] = None

    return data
