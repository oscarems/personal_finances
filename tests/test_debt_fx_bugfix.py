"""Tests for bugfix-debt-fx: rate units, FX CC balance, capitalization, FX fallback."""
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finance_app.database import Base, _MIGRATION_COLUMNS
from finance_app.domain.fx.service import (
    ConversionResult,
    convert_to_cop,
    convert_to_cop_result,
)
from finance_app.models import Account, Currency, Debt, ExchangeRate
from finance_app.services.debt.amortization_engine import AmortizationEngine
from finance_app.services.debt.helpers import (
    effective_monthly_interest_rate,
    get_credit_card_current_balance,
    normalize_rate_units,
)
from finance_app.services.debt.simulator import _build_states, simulate_payoff
from finance_app.services.exchange_rate_service import get_rate_result


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


# ── BUG-010: rate units unified ─────────────────────────────────────────────


def test_normalize_rate_units_percent_vs_decimal():
    assert normalize_rate_units(1.9) == pytest.approx(0.019)
    assert normalize_rate_units(0.019) == pytest.approx(0.019)
    assert normalize_rate_units(1.0) == pytest.approx(1.0)  # boundary: treat as decimal


def test_simulator_uses_effective_monthly_heuristic_for_decimal_mir():
    """monthly_interest_rate <= 1 must NOT be divided by 100 again."""
    debt = SimpleNamespace(
        id=1,
        name="CC",
        current_balance=1000.0,
        monthly_interest_rate=0.019,  # already decimal 1.9%/mo
        annual_interest_rate=None,
        interest_rate=None,
        monthly_payment=50.0,
        minimum_payment=None,
        min_payment_percentage=None,
        currency_code="COP",
    )
    expected = effective_monthly_interest_rate(debt)
    states = _build_states([debt])
    assert float(states[0].monthly_rate) == pytest.approx(expected)
    assert float(states[0].monthly_rate) == pytest.approx(0.019)


def test_simulator_percent_mir_matches_helpers():
    debt = SimpleNamespace(
        id=2,
        name="CC%",
        current_balance=1000.0,
        monthly_interest_rate=1.9,  # percent
        annual_interest_rate=None,
        interest_rate=None,
        monthly_payment=50.0,
        minimum_payment=None,
        min_payment_percentage=None,
        currency_code="COP",
    )
    states = _build_states([debt])
    assert float(states[0].monthly_rate) == pytest.approx(0.019)
    result = simulate_payoff([debt], extra_payment=0, strategy="none")
    assert result["total_interest"] > 0


# ── BUG-011: CC balance FX ──────────────────────────────────────────────────


def test_cc_balance_converts_account_currency_to_debt_currency():
    db = _session()
    today = date.today()
    db.add_all([
        Currency(id=1, code="COP", symbol="$", name="Peso", is_base=True, decimals=0),
        Currency(id=2, code="USD", symbol="US$", name="Dollar", is_base=False, decimals=2),
        ExchangeRate(from_currency="USD", to_currency="COP", rate=4000.0, date=today),
    ])
    account = Account(
        id=1,
        name="Visa USD",
        type="credit_card",
        currency_id=2,
        balance=-100.0,  # owe 100 USD
    )
    db.add(account)
    debt = Debt(
        account_id=1,
        name="Visa",
        debt_type="credit_card",
        currency_code="COP",
        original_amount=400000.0,
        current_balance=0.0,
        start_date=today,
        is_active=True,
    )
    db.add(debt)
    db.commit()
    db.refresh(debt)

    # Without conversion would be 100; with FX must be ~400_000 COP.
    balance = get_credit_card_current_balance(debt, db)
    assert balance == pytest.approx(400000.0, rel=1e-6)


# ── BUG-012: capitalize unpaid interest ─────────────────────────────────────


def test_amortization_capitalizes_when_payment_below_interest():
    debt = Debt(
        account_id=1,
        name="Loan",
        debt_type="credit_loan",
        currency_code="COP",
        original_amount=100_000.0,
        current_balance=100_000.0,
        start_date=date(2024, 1, 1),
        term_months=12,
        monthly_payment=500.0,  # well below first-month interest at 24%/yr
        annual_interest_rate=24.0,  # percent → ~1.8%/mo ≈ 1800 on 100k
        notes="cuota_fija",
        is_active=True,
    )
    engine = AmortizationEngine()
    schedule = engine.generate_schedule(debt, mode="plan")
    assert len(schedule) >= 1
    row0 = schedule[0]
    assert row0["interest"] > row0["payment"]
    assert row0["principal"] == pytest.approx(0.0, abs=0.01)
    # ending = opening + interest - payment  (> opening)
    expected_ending = row0["opening_balance"] + row0["interest"] - row0["payment"]
    assert row0["ending_balance"] == pytest.approx(expected_ending, abs=0.02)
    assert row0["ending_balance"] > row0["opening_balance"]


# ── BUG-013: confirmed_balance migrations ───────────────────────────────────


def test_confirmed_balance_in_migration_columns():
    cols = {(t, c) for t, c, _ in _MIGRATION_COLUMNS}
    assert ("debts", "confirmed_balance") in cols
    assert ("debts", "confirmed_balance_date") in cols
    defs = {c: d for t, c, d in _MIGRATION_COLUMNS if t == "debts"}
    assert "NUMERIC" in defs["confirmed_balance"].upper()
    assert "DATE" in defs["confirmed_balance_date"].upper()


# ── BUG-014: FX fallback flagged ────────────────────────────────────────────


def test_fx_unknown_currency_flags_identity_fallback():
    db = _session()
    db.add(Currency(id=1, code="COP", symbol="$", name="Peso", is_base=True, decimals=0))
    db.commit()

    meta = get_rate_result(db, "ZZZ", "COP", date(2024, 6, 1))
    assert meta.used_fallback is True
    assert meta.source == "fallback_identity"
    assert meta.rate == 1.0

    result = convert_to_cop_result(100, "ZZZ", date(2024, 6, 1), db=db)
    assert isinstance(result, ConversionResult)
    assert result.used_fallback is True
    assert result.rate_source == "fallback_identity"
    assert float(result.amount) == pytest.approx(100.0)

    # Backward-compatible helper still returns the amount (with warning logged).
    assert float(convert_to_cop(100, "ZZZ", date(2024, 6, 1), db=db)) == pytest.approx(100.0)


# ── BUG-025: dynamic minimum projection + CC FX balance ─────────────────────


def test_minimum_projection_recalculates_as_balance_declines():
    """Dynamic % minimum must shrink with balance → less total paid than a fixed opening min."""
    from finance_app.services.debt.cost_analysis import _project_minimum_payment

    debt = Debt(
        account_id=1,
        name="Loan",
        debt_type="credit_loan",
        currency_code="COP",
        original_amount=1_000_000.0,
        current_balance=1_000_000.0,
        start_date=date(2024, 1, 1),
        monthly_interest_rate=1.5,  # 1.5%/mo
        minimum_payment=None,
        min_payment_percentage=5.0,  # 5% of current balance each month
        is_active=True,
    )

    result = _project_minimum_payment(debt, db=None)
    assert result["months_if_minimum"] is not None
    assert result["months_if_minimum"] > 1
    opening_min = result["monthly_minimum"]
    assert opening_min == pytest.approx(1_000_000 * 0.05, abs=1.0)

    # Fixed-opening-min baseline would pay opening_min every month;
    # dynamic mins shrink so total paid is strictly less.
    assert result["total_paid_if_minimum"] < opening_min * result["months_if_minimum"]


def test_minimum_projection_uses_fx_converted_cc_balance():
    from finance_app.services.debt.cost_analysis import _project_minimum_payment
    from finance_app.services.debt.helpers import get_credit_card_current_balance

    db = _session()
    today = date.today()
    db.add_all([
        Currency(id=1, code="COP", symbol="$", name="Peso", is_base=True, decimals=0),
        Currency(id=2, code="USD", symbol="US$", name="Dollar", is_base=False, decimals=2),
        ExchangeRate(from_currency="USD", to_currency="COP", rate=4000.0, date=today),
    ])
    db.add(Account(
        id=1, name="Visa USD", type="credit_card", currency_id=2, balance=-50.0,
    ))
    debt = Debt(
        account_id=1,
        name="Visa",
        debt_type="credit_card",
        currency_code="COP",
        original_amount=200_000.0,
        current_balance=1.0,  # stale / wrong — must NOT be used
        start_date=today,
        monthly_interest_rate=2.0,
        min_payment_percentage=5.0,
        is_active=True,
    )
    db.add(debt)
    db.commit()
    db.refresh(debt)

    assert get_credit_card_current_balance(debt, db) == pytest.approx(200_000.0)
    result = _project_minimum_payment(debt, db=db)
    # Opening balance 50 USD * 4000 = 200_000 COP → 5% min = 10_000
    assert result["monthly_minimum"] == pytest.approx(10_000.0, abs=1.0)
    assert result["months_if_minimum"] is not None
    assert result["months_if_minimum"] > 1

# ── BUG-030: budget converter multi-currency via convert_currency ───────────


def test_budget_converter_eur_to_cop_with_db():
    from finance_app.services.budget_service import _make_currency_converter

    db = _session()
    today = date.today()
    db.add_all([
        Currency(id=1, code="COP", symbol="$", name="Peso", is_base=True, decimals=0),
        Currency(id=2, code="USD", symbol="US$", name="Dollar", is_base=False, decimals=2),
        Currency(id=3, code="EUR", symbol="€", name="Euro", is_base=False, decimals=2),
        ExchangeRate(from_currency="USD", to_currency="COP", rate=4000.0, date=today),
        ExchangeRate(from_currency="USD", to_currency="EUR", rate=0.92, date=today),
    ])
    db.commit()

    # Without db: EUR→COP is identity (legacy limitation)
    no_db = _make_currency_converter("COP", 4000.0)
    assert no_db(100.0, "EUR") == 100.0

    # With db: EUR→COP via USD pivot
    with_db = _make_currency_converter("COP", 4000.0, db=db)
    converted = with_db(100.0, "EUR")
    assert converted == pytest.approx(100 / 0.92 * 4000, rel=1e-6)
    assert with_db(100.0, "USD") == pytest.approx(400_000.0)
