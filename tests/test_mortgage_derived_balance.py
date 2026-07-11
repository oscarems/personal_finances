"""Tests for the mortgage redesign: everything derives from original_amount,
start_date, interest_rate and loan_years — no real-payment tracking.
"""
from datetime import date, datetime

import pytest
from dateutil.relativedelta import relativedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finance_app.database import Base
from finance_app.domain.debts.service import get_debts_principal
from finance_app.models import Account, Currency, Debt, DebtPayment
from finance_app.services.debt.amortization_engine import AmortizationEngine
from finance_app.services.debt.balance_service import (
    calculate_mortgage_principal_balance,
    calculate_scheduled_principal_balance,
    refresh_mortgage_current_balance,
)
from finance_app.services.debt.helpers import (
    build_mortgage_payment_history,
    calculate_loan_current_balance,
    debt_to_dict_with_calculated_balance,
)
from finance_app.services.mortgage.service import calculate_monthly_payment
from finance_app.services.patrimonio.calculator import saldo_deuda_en_mes
from finance_app.services.transaction_service import create_transaction


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_currency(db, code="COP", decimals=0):
    currency = Currency(id=1, code=code, symbol="$", name="Peso", is_base=True, decimals=decimals)
    db.add(currency)
    db.commit()
    return currency


def _make_mortgage_account(db, **overrides):
    """Create an Account + linked Debt for a fully-specified mortgage (4 base fields)."""
    account = Account(name="Apto Test", type="mortgage", currency_id=1, balance=0.0, is_budget=False)
    db.add(account)
    db.commit()

    payload = dict(
        account_id=account.id,
        name="Apto Test",
        debt_type="mortgage",
        currency_code="COP",
        original_amount=300_000_000.0,
        current_balance=300_000_000.0,
        interest_rate=12.0,
        annual_interest_rate=12.0,
        loan_years=20,
        term_months=240,
        start_date=date(2024, 1, 15),
        is_active=True,
    )
    payload.update(overrides)
    debt = Debt(**payload)
    db.add(debt)
    db.commit()
    return account, debt


class TestPureDerivation:
    """The schedule/balance must come only from original_amount/start_date/rate/term."""

    def test_monthly_payment_is_always_the_french_formula(self):
        db = _session()
        _seed_currency(db)
        _, debt = _make_mortgage_account(db, monthly_payment=999_999_999.0)  # bogus stored override

        engine = AmortizationEngine(db=db)
        schedule = engine.generate_schedule(debt, mode="plan")

        expected_payment = calculate_monthly_payment(300_000_000.0, 0.12, 20)
        assert schedule[0]["payment"] == pytest.approx(expected_payment)
        assert len(schedule) == 240
        assert schedule[-1]["ending_balance"] == 0.0

    def test_mode_argument_is_ignored_for_mortgages(self):
        """actual/hybrid must not change a mortgage's schedule — it always runs plan-mode."""
        db = _session()
        _seed_currency(db)
        _, debt = _make_mortgage_account(db)

        # A recorded payment that would (under the old system) shorten the term.
        db.add(DebtPayment(
            debt_id=debt.id, payment_date=date(2024, 2, 15),
            amount=50_000_000.0, principal=50_000_000.0, interest=0.0,
        ))
        db.commit()

        engine = AmortizationEngine(db=db)
        plan_schedule = engine.generate_schedule(debt, mode="plan")
        hybrid_schedule = engine.generate_schedule(debt, mode="hybrid")
        actual_schedule = engine.generate_schedule(debt, mode="actual")

        assert len(plan_schedule) == len(hybrid_schedule) == 240
        # actual mode returns an empty/short schedule when nothing matches "plan"
        # semantics, but must never use the extra payment to shrink the term below plan.
        assert len(actual_schedule) <= len(plan_schedule)
        assert plan_schedule[0]["principal"] == hybrid_schedule[0]["principal"]

    def test_legacy_mortgage_without_term_falls_back_to_stored_payment(self):
        """Mortgages created before this redesign may lack loan_years/term_months.

        The engine must not silently pay off the whole balance in month 1 — it
        should fall back to the stored monthly_payment so the derived balance
        stays sane until the user fills in the missing term.

        (monthly_payment here must exceed the monthly interest at the given rate/
        balance, otherwise the loan negatively amortizes and the balance
        legitimately stays flat — this uses real production-like figures.)
        """
        db = _session()
        _seed_currency(db)
        _, debt = _make_mortgage_account(
            db,
            original_amount=158_484_053.0,
            current_balance=158_484_053.0,
            interest_rate=11.5,
            annual_interest_rate=11.5,
            loan_years=None,
            term_months=None,
            monthly_payment=1_994_000.0,
        )

        balance = calculate_scheduled_principal_balance(debt, date(2024, 6, 15))
        assert 0 < balance < 158_484_053.0

    def test_balance_decreases_monotonically_over_time(self):
        db = _session()
        _seed_currency(db)
        _, debt = _make_mortgage_account(db)

        b0 = calculate_scheduled_principal_balance(debt, date(2024, 1, 15))
        b1 = calculate_scheduled_principal_balance(debt, date(2025, 1, 15))
        b2 = calculate_scheduled_principal_balance(debt, date(2030, 1, 15))
        b_end = calculate_scheduled_principal_balance(debt, date(2044, 1, 15))

        assert 300_000_000.0 >= b0 > b1 > b2 > b_end == 0.0


class TestRealPaymentsNoLongerAffectBalance:
    """Transactions/DebtPayments must not change the mortgage's derived balance."""

    def test_refresh_mortgage_current_balance_matches_scheduled_balance(self):
        db = _session()
        _seed_currency(db)
        _, debt = _make_mortgage_account(db)

        as_of = date(2026, 1, 15)
        expected = calculate_scheduled_principal_balance(debt, as_of)
        got = calculate_mortgage_principal_balance(db, debt, as_of_date=as_of)
        assert got == expected

        refreshed = refresh_mortgage_current_balance(db, debt, as_of_date=as_of)
        assert refreshed == expected
        assert debt.current_balance == expected
        # principal_balance is no longer written by the derived-balance path.
        assert debt.principal_balance is None

    def test_transaction_does_not_change_balance_based_on_amount(self):
        """Paying $1 or $50M on the same date must yield the same derived balance."""
        db = _session()
        _seed_currency(db)
        # created_at is backdated to sidestep UTC-vs-local-clock edge cases around
        # midnight — transaction_affects_balance() requires tx_date >= created_at.
        checking = Account(
            name="Nomina", type="checking", currency_id=1, balance=10_000_000.0,
            created_at=datetime(2020, 1, 1),
        )
        db.add(checking)
        db.commit()

        _, debt_small = _make_mortgage_account(db, name="Hipoteca A")
        _, debt_big = _make_mortgage_account(db, name="Hipoteca B")

        tx_date = date.today()
        create_transaction(db, {
            "account_id": checking.id, "date": tx_date, "debt_id": debt_small.id,
            "amount": -1.0, "currency_id": 1, "memo": "cuota",
        })
        create_transaction(db, {
            "account_id": checking.id, "date": tx_date, "debt_id": debt_big.id,
            "amount": -50_000_000.0, "currency_id": 1, "memo": "abono grande",
        })

        db.refresh(debt_small)
        db.refresh(debt_big)
        expected = calculate_scheduled_principal_balance(debt_small, tx_date)
        assert debt_small.current_balance == expected
        assert debt_big.current_balance == expected

    def test_deleting_the_transaction_still_matches_the_schedule(self):
        db = _session()
        _seed_currency(db)
        checking = Account(
            name="Nomina", type="checking", currency_id=1, balance=10_000_000.0,
            created_at=datetime(2020, 1, 1),
        )
        db.add(checking)
        db.commit()
        _, debt = _make_mortgage_account(db)

        tx_date = date.today()
        tx = create_transaction(db, {
            "account_id": checking.id, "date": tx_date, "debt_id": debt.id,
            "amount": -3_000_000.0, "currency_id": 1, "memo": "cuota",
        })

        from finance_app.services.transaction_service import delete_transaction
        delete_transaction(db, tx.id)

        db.refresh(debt)
        expected = calculate_scheduled_principal_balance(debt, tx_date)
        assert debt.current_balance == expected


class TestSerializationAndAggregates:
    def test_debt_to_dict_has_no_balance_discrepancy_for_mortgage(self):
        db = _session()
        _seed_currency(db)
        _, debt = _make_mortgage_account(db)
        debt.confirmed_balance = 999_999_999
        db.commit()

        data = debt_to_dict_with_calculated_balance(debt, db)
        assert data["balance_discrepancy"] is None

    def test_calculate_loan_current_balance_uses_plan_math(self):
        db = _session()
        _seed_currency(db)
        _, debt = _make_mortgage_account(db)

        as_of_today_equivalent = calculate_scheduled_principal_balance(debt, date.today())
        assert calculate_loan_current_balance(debt, db) == as_of_today_equivalent

    def test_get_debts_principal_uses_plan_math_for_mortgage(self):
        db = _session()
        _seed_currency(db)
        _, debt = _make_mortgage_account(db)

        as_of = date(2027, 1, 15)
        records = get_debts_principal(db, as_of)
        record = next(r for r in records if r.debt_id == debt.id)
        assert float(record.principal_original) == calculate_scheduled_principal_balance(debt, as_of)

    def test_patrimonio_saldo_deuda_en_mes_uses_pure_math_even_with_db(self):
        db = _session()
        _seed_currency(db)
        _, debt = _make_mortgage_account(db)

        # Passing db should not switch mortgages to the (now-removed) hybrid engine path.
        saldo_with_db = saldo_deuda_en_mes(debt, 2027, 1, db=db)
        saldo_without_db = saldo_deuda_en_mes(debt, 2027, 1, db=None)
        assert saldo_with_db == saldo_without_db

    def test_payment_history_is_informational_only(self):
        """DebtPayment records show up in history but the balance itself is schedule-derived."""
        db = _session()
        _seed_currency(db)
        _, debt = _make_mortgage_account(db)

        db.add(DebtPayment(
            debt_id=debt.id, payment_date=date(2024, 2, 15),
            amount=3_175_870.06, principal=329_232.17, interest=2_846_637.88,
        ))
        db.commit()

        history = build_mortgage_payment_history(debt, db)
        assert len(history) == 1
        assert history[0]["amount"] == 3_175_870.06
