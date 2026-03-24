from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finance_app.database import Base
from finance_app.services.debt.timeline import build_debt_principal_timeline
from finance_app.models import Currency, ExchangeRate, Debt, DebtPayment


def _make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_currencies(db):
    cop = Currency(id=1, code="COP", symbol="$", name="Peso", is_base=True, decimals=0)
    usd = Currency(id=2, code="USD", symbol="US$", name="Dollar", is_base=False, decimals=2)
    db.add_all([cop, usd])
    db.add(ExchangeRate(from_currency="USD", to_currency="COP", rate=4000.0, date=date(2024, 1, 1)))
    db.commit()


def test_principal_timeline_with_fixed_payments():
    db = _make_session()
    _seed_currencies(db)

    debt = Debt(
        account_id=1,
        name="Prestamo",
        debt_type="credit_loan",
        currency_code="COP",
        original_amount=1000.0,
        current_balance=1000.0,
        interest_rate=12.0,
        start_date=date(2024, 1, 1),
        is_active=True,
    )
    db.add(debt)
    db.flush()

    payments = [
        DebtPayment(debt_id=debt.id, payment_date=date(2024, 1, 15), amount=100.0),
        DebtPayment(debt_id=debt.id, payment_date=date(2024, 2, 15), amount=100.0),
        DebtPayment(debt_id=debt.id, payment_date=date(2024, 3, 15), amount=100.0),
    ]
    db.add_all(payments)
    db.commit()

    timeline = build_debt_principal_timeline(
        start_month=date(2024, 1, 1),
        end_month=date(2024, 3, 1),
        debts=[debt],
        include_projection=False,
        currency_id=1,
        exchange_rate=1.0,
        currency_map={"COP": 1},
        today=date(2024, 3, 20),
    )

    jan = timeline[0]["debts"][str(debt.id)]
    feb = timeline[1]["debts"][str(debt.id)]
    mar = timeline[2]["debts"][str(debt.id)]

    assert jan["principal_end"] == pytest.approx(900.0, rel=1e-3)
    assert feb["principal_end"] == pytest.approx(800.0, rel=1e-3)
    assert mar["principal_end"] == pytest.approx(700.0, rel=1e-3)


def test_principal_timeline_without_interest():
    db = _make_session()
    _seed_currencies(db)

    debt = Debt(
        account_id=1,
        name="Prestamo",
        debt_type="credit_loan",
        currency_code="COP",
        original_amount=1000.0,
        current_balance=1000.0,
        start_date=date(2024, 1, 1),
        is_active=True,
    )
    db.add(debt)
    db.flush()
    db.add(DebtPayment(debt_id=debt.id, payment_date=date(2024, 1, 10), amount=50.0))
    db.commit()

    timeline = build_debt_principal_timeline(
        start_month=date(2024, 1, 1),
        end_month=date(2024, 1, 1),
        debts=[debt],
        include_projection=False,
        currency_id=1,
        exchange_rate=1.0,
        currency_map={"COP": 1},
        today=date(2024, 1, 20),
    )

    jan = timeline[0]["debts"][str(debt.id)]
    assert jan["interest_accrued"] == 0.0
    assert jan["principal_end"] == pytest.approx(950.0, rel=1e-3)


def test_principal_timeline_caps_at_zero():
    db = _make_session()
    _seed_currencies(db)

    debt = Debt(
        account_id=1,
        name="Prestamo",
        debt_type="credit_loan",
        currency_code="COP",
        original_amount=100.0,
        current_balance=100.0,
        start_date=date(2024, 1, 1),
        is_active=True,
    )
    db.add(debt)
    db.flush()
    db.add(DebtPayment(debt_id=debt.id, payment_date=date(2024, 1, 5), amount=120.0))
    db.commit()

    timeline = build_debt_principal_timeline(
        start_month=date(2024, 1, 1),
        end_month=date(2024, 1, 1),
        debts=[debt],
        include_projection=False,
        currency_id=1,
        exchange_rate=1.0,
        currency_map={"COP": 1},
        today=date(2024, 1, 20),
    )

    jan = timeline[0]["debts"][str(debt.id)]
    assert jan["principal_end"] == 0.0


def test_credit_cards_are_excluded_from_principal_timeline():
    db = _make_session()
    _seed_currencies(db)

    credit_card = Debt(
        account_id=1,
        name="Visa",
        debt_type="credit_card",
        currency_code="COP",
        original_amount=500.0,
        current_balance=500.0,
        start_date=date(2024, 1, 1),
        is_active=True,
    )
    loan = Debt(
        account_id=2,
        name="Prestamo",
        debt_type="credit_loan",
        currency_code="COP",
        original_amount=800.0,
        current_balance=800.0,
        start_date=date(2024, 1, 1),
        is_active=True,
    )
    db.add_all([credit_card, loan])
    db.commit()

    timeline = build_debt_principal_timeline(
        start_month=date(2024, 1, 1),
        end_month=date(2024, 1, 1),
        debts=[credit_card, loan],
        include_projection=False,
        currency_id=1,
        exchange_rate=1.0,
        currency_map={"COP": 1},
        today=date(2024, 1, 20),
    )

    jan = timeline[0]
    assert str(credit_card.id) not in jan["debts"]
    assert jan["total_principal_end"] == pytest.approx(800.0, rel=1e-3)
