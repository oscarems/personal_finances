from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finance_app.database import Base
from finance_app.models import Debt, DebtPayment
from finance_app.services.amortization_engine import AmortizationEngine


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _base_debt(**kwargs):
    payload = {
        "account_id": 1,
        "name": "Hipoteca Test",
        "debt_type": "mortgage",
        "currency_code": "COP",
        "original_amount": 100000.0,
        "current_balance": 100000.0,
        "start_date": date(2024, 1, 1),
        "loan_years": 1,
        "is_active": True,
    }
    payload.update(kwargs)
    return Debt(**payload)


def test_fixed_payment_schedule_ends_near_zero():
    debt = _base_debt(annual_interest_rate=0.12)
    engine = AmortizationEngine()

    schedule = engine.generate_schedule(debt, mode="plan")

    assert len(schedule) == 12
    assert schedule[-1]["ending_balance"] == pytest.approx(0.0, abs=0.01)


def test_monthly_rate_direct_matches_nominal_annual_equivalent():
    debt_monthly = _base_debt(annual_interest_rate=0.01, notes="tasa_mensual cuota_fija")

    effective_engine = AmortizationEngine(annual_rate_convention="nominal")
    schedule_a = effective_engine.generate_schedule(debt_monthly, mode="plan")

    debt_equivalent = _base_debt(annual_interest_rate=0.12, notes="fixed_payment")
    schedule_b = effective_engine.generate_schedule(debt_equivalent, mode="plan")

    assert schedule_a[0]["interest"] == pytest.approx(schedule_b[0]["interest"], abs=0.01)
    assert schedule_a[-1]["ending_balance"] == pytest.approx(schedule_b[-1]["ending_balance"], abs=0.01)


def test_zero_rate():
    debt = _base_debt(annual_interest_rate=0.0)
    engine = AmortizationEngine()

    schedule = engine.generate_schedule(debt, mode="plan")

    assert all(item["interest"] == 0 for item in schedule)
    assert schedule[-1]["ending_balance"] == 0.0


def test_extra_payments_reduce_term():
    db = _session()
    debt = _base_debt(annual_interest_rate=0.12)
    db.add(debt)
    db.flush()

    db.add(DebtPayment(debt_id=debt.id, payment_date=date(2024, 1, 5), amount=30000.0, principal=30000.0, interest=0.0))
    db.commit()

    engine = AmortizationEngine(db=db)
    plan_len = len(engine.generate_schedule(debt, mode="plan"))
    hybrid_len = len(engine.generate_schedule(debt, mode="hybrid"))

    assert hybrid_len < plan_len


def test_rounding_never_negative_and_last_payment_adjusted():
    debt = _base_debt(annual_interest_rate=0.01, original_amount=1234.56, current_balance=1234.56)
    engine = AmortizationEngine()

    schedule = engine.generate_schedule(debt, mode="plan")

    assert all(item["ending_balance"] >= 0 for item in schedule)
    assert schedule[-1]["ending_balance"] == 0.0
