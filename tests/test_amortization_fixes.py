"""Tests for the three amortization-module bug fixes."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from finance_app.database import Base
from finance_app.models import Debt, DebtAmortizationMonthly
from finance_app.services.debt.amortization_engine import AmortizationEngine
from finance_app.services.debt.amortization_service import ensure_debt_amortization_records


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _base_debt(**kwargs):
    payload = {
        "account_id": 1,
        "name": "Test Loan",
        "debt_type": "credit_loan",
        "currency_code": "COP",
        "original_amount": 120000.0,
        "current_balance": 120000.0,
        "start_date": date(2026, 1, 1),
        "loan_years": 1,
        "annual_interest_rate": 12.0,
        "is_active": True,
    }
    payload.update(kwargs)
    return Debt(**payload)


# ── Bug 1: ensure_debt_amortization_records updates when status differs ──


def test_status_change_triggers_update():
    """When principal_remaining is the same but status changed, the record should update."""
    db = _session()
    debt = _base_debt()
    db.add(debt)
    db.flush()

    month = date(2026, 1, 1)

    # Insert an existing record with status "proyeccion" and a specific balance
    existing = DebtAmortizationMonthly(
        debt_id=debt.id,
        snapshot_month="2026-01",
        as_of_date=month,
        currency_code="COP",
        principal_payment=1000.0,
        interest_payment=500.0,
        total_payment=1500.0,
        principal_remaining=119000.0,
        interest_rate_calculated=1.0,
        status="proyeccion",
    )
    db.add(existing)
    db.commit()

    # Generate a schedule that will produce "pagado" for that month and the
    # same principal_remaining value, by mocking the engine.
    fake_schedule = [
        {
            "date": month,
            "is_paid_real": True,
            "interest": 500.0,
            "opening_balance": 120000.0,
            "principal": 1000.0,
            "payment": 1500.0,
            "ending_balance": 119000.0,
        }
    ]

    with patch.object(AmortizationEngine, "generate_schedule", return_value=fake_schedule):
        ensure_debt_amortization_records(
            db, start_month=month, end_month=month, months_ahead=0, today=month,
        )

    record = db.query(DebtAmortizationMonthly).filter_by(debt_id=debt.id, as_of_date=month).one()
    assert record.status == "pagado"


# ── Bug 2: fixed_payment skips redundant _planned_payment call ──


def test_fixed_payment_uses_base_payment_directly():
    """For fixed_payment with a precomputed base_payment, _planned_payment should not be called in the loop."""
    debt = _base_debt(
        monthly_payment=10000.0,
        notes="cuota_fija",
    )
    engine = AmortizationEngine()

    with patch.object(engine, "_planned_payment", wraps=engine._planned_payment) as spy:
        schedule = engine.generate_schedule(debt, mode="plan")

        # _planned_payment should only be called once (for the initial base_payment
        # computation at the top, since monthly_payment > 0 means base_payment > 0,
        # so actually it should NOT be called even once in the loop).
        # With the fix, the loop bypasses _planned_payment entirely for fixed_payment.
        # The initial base_payment is set from debt.monthly_payment directly (no call),
        # so _planned_payment should be called 0 times.
        assert spy.call_count == 0

    # Verify schedule still produces correct results
    assert len(schedule) > 0
    assert schedule[0]["payment"] == pytest.approx(10000.0, abs=0.01)


# ── Bug 3: monetary columns use Numeric instead of Float ──


def test_monetary_columns_are_numeric():
    """DebtAmortizationMonthly monetary columns should be Numeric, not Float."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    columns = {col["name"]: col for col in inspector.get_columns("debt_amortization_monthly")}

    numeric_fields = [
        "principal_payment",
        "interest_payment",
        "total_payment",
        "principal_remaining",
        "interest_rate_calculated",
    ]
    for field in numeric_fields:
        col_type = type(columns[field]["type"])
        # SQLAlchemy reflects Numeric as NUMERIC on SQLite
        assert col_type.__name__ in ("NUMERIC", "Numeric"), (
            f"Column {field} should be NUMERIC, got {col_type.__name__}"
        )
