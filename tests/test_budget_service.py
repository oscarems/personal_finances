from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finance_app.database import Base
from finance_app.models import Account, Category, CategoryGroup, Currency, ExchangeRate
from finance_app.services.budget_service import (
    assign_money_to_category,
    calculate_ready_to_assign,
    get_or_create_budget_month,
    initialize_month,
    recalculate_budget_available,
)
from finance_app.services.transaction_service import create_transaction


def _make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_base(db):
    cop = Currency(id=1, code="COP", symbol="$", name="Peso", is_base=True, decimals=0)
    usd = Currency(id=2, code="USD", symbol="US$", name="Dollar", is_base=False, decimals=2)
    group = CategoryGroup(name="Gastos", sort_order=1, is_income=False)
    expense_cat = Category(name="Mercado", category_group=group, rollover_type="reset")
    savings_cat = Category(name="Ahorro Emergencia", category_group=group, rollover_type="accumulate")
    db.add_all([cop, usd, group, expense_cat, savings_cat])
    db.add(ExchangeRate(from_currency="USD", to_currency="COP", rate=4000.0, date=date(2024, 1, 1)))
    db.commit()
    return cop, usd, expense_cat, savings_cat


# ---------------------------------------------------------------------------
# recalculate_budget_available
# ---------------------------------------------------------------------------

def test_recalculate_available_for_expense_category_is_assigned_minus_spent():
    db = _make_session()
    _, _, expense_cat, _ = _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=1_000_000, created_at=datetime(2020, 1, 1))
    db.add(account)
    db.commit()

    month = date.today().replace(day=1)
    budget = get_or_create_budget_month(db, expense_cat.id, month, 1)
    budget.assigned = 200_000
    db.commit()

    create_transaction(db, {
        "account_id": account.id,
        "date": date.today(),
        "category_id": expense_cat.id,
        "amount": -50_000,
        "currency_id": 1,
    })

    recalculate_budget_available(db, budget)
    db.commit()

    assert budget.activity == -50_000
    assert budget.available == 150_000  # asignado - gastado


def test_recalculate_available_for_savings_category_includes_prior_rollover():
    db = _make_session()
    _, _, _, savings_cat = _seed_base(db)
    account = Account(name="Cuenta", type="savings", currency_id=1, balance=1_000_000, created_at=datetime(2020, 1, 1))
    db.add(account)
    db.commit()

    prev_month = date.today().replace(day=1)
    # Go back a month manually using the previous month's first day
    from dateutil.relativedelta import relativedelta
    prev_month = prev_month - relativedelta(months=1)
    curr_month = prev_month + relativedelta(months=1)

    prev_budget = get_or_create_budget_month(db, savings_cat.id, prev_month, 1)
    prev_budget.assigned = 100_000
    prev_budget.activity = -20_000
    prev_budget.available = 80_000  # disponible del mes anterior
    db.commit()

    curr_budget = get_or_create_budget_month(db, savings_cat.id, curr_month, 1)
    curr_budget.assigned = 50_000
    db.commit()

    create_transaction(db, {
        "account_id": account.id,
        "date": curr_month,
        "category_id": savings_cat.id,
        "amount": -10_000,
        "currency_id": 1,
    })

    recalculate_budget_available(db, curr_budget)
    db.commit()

    # disponible = disponible_mes_anterior + asignado + actividad(-gastado)
    assert curr_budget.activity == -10_000
    assert curr_budget.available == 80_000 + 50_000 - 10_000


# ---------------------------------------------------------------------------
# _cascade_future_months (via assign_money_to_category)
# ---------------------------------------------------------------------------

def test_cascade_propagates_assigned_to_future_non_overridden_months():
    db = _make_session()
    _, _, expense_cat, _ = _seed_base(db)
    from dateutil.relativedelta import relativedelta

    month1 = date.today().replace(day=1)
    month2 = month1 + relativedelta(months=1)
    month3 = month1 + relativedelta(months=2)

    # Pre-create future months (not overridden by the user)
    get_or_create_budget_month(db, expense_cat.id, month2, 1)
    get_or_create_budget_month(db, expense_cat.id, month3, 1)
    db.commit()

    assign_money_to_category(db, expense_cat.id, month1, 1, 300_000)

    b2 = get_or_create_budget_month(db, expense_cat.id, month2, 1)
    b3 = get_or_create_budget_month(db, expense_cat.id, month3, 1)
    assert b2.assigned == 300_000
    assert b3.assigned == 300_000


def test_cascade_does_not_overwrite_manually_edited_future_month():
    db = _make_session()
    _, _, expense_cat, _ = _seed_base(db)
    from dateutil.relativedelta import relativedelta

    month1 = date.today().replace(day=1)
    month2 = month1 + relativedelta(months=1)

    # Month2 is manually edited by the user first (assigned_overridden=True)
    assign_money_to_category(db, expense_cat.id, month2, 1, 999_000)

    # Now edit month1 — should NOT overwrite month2's manual value
    assign_money_to_category(db, expense_cat.id, month1, 1, 300_000)

    b2 = get_or_create_budget_month(db, expense_cat.id, month2, 1)
    assert b2.assigned == 999_000


# ---------------------------------------------------------------------------
# listo_para_asignar (calculate_ready_to_assign)
# ---------------------------------------------------------------------------

def test_ready_to_assign_is_account_balances_minus_available_in_budget():
    db = _make_session()
    _, _, expense_cat, _ = _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=1_000_000, is_budget=True, is_closed=False)
    db.add(account)
    db.commit()

    month = date.today().replace(day=1)
    assign_money_to_category(db, expense_cat.id, month, 1, 300_000)

    ready = calculate_ready_to_assign(db, month, 1)

    assert ready == 1_000_000 - 300_000


def test_ready_to_assign_excludes_debt_accounts():
    db = _make_session()
    _, _, expense_cat, _ = _seed_base(db)
    budget_account = Account(name="Cuenta", type="checking", currency_id=1, balance=500_000, is_budget=True, is_closed=False)
    cc_account = Account(name="Tarjeta", type="credit_card", currency_id=1, balance=-200_000, is_budget=True, is_closed=False)
    db.add_all([budget_account, cc_account])
    db.commit()

    month = date.today().replace(day=1)
    ready = calculate_ready_to_assign(db, month, 1)

    assert ready == 500_000


# ---------------------------------------------------------------------------
# initialize_month
# ---------------------------------------------------------------------------

def test_initialize_month_inherits_assigned_for_reset_category():
    db = _make_session()
    _, _, expense_cat, _ = _seed_base(db)
    from dateutil.relativedelta import relativedelta

    prev_month = date.today().replace(day=1) - relativedelta(months=1)
    target_month = prev_month + relativedelta(months=1)

    prev_budget = get_or_create_budget_month(db, expense_cat.id, prev_month, 1)
    prev_budget.assigned = 250_000
    prev_budget.activity = -100_000
    db.commit()

    result = initialize_month(db, target_month.year, target_month.month)

    assert result["created"] == 1
    new_budget = get_or_create_budget_month(db, expense_cat.id, target_month, 1)
    assert new_budget.assigned == 250_000  # reset: hereda asignado tal cual


def test_initialize_month_computes_initial_amount_for_savings_category_from_prior_available():
    db = _make_session()
    _, _, _, savings_cat = _seed_base(db)
    from dateutil.relativedelta import relativedelta

    account = Account(name="Cuenta", type="savings", currency_id=1, balance=1_000_000, created_at=datetime(2020, 1, 1))
    db.add(account)
    db.commit()

    prev_month = date.today().replace(day=1) - relativedelta(months=1)
    target_month = prev_month + relativedelta(months=1)

    prev_budget = get_or_create_budget_month(db, savings_cat.id, prev_month, 1)
    prev_budget.assigned = 100_000
    db.commit()

    # initialize_month recalculates prev_budget.activity from real transactions,
    # so we create one instead of setting .activity directly (which would be
    # overwritten by the recalculation).
    create_transaction(db, {
        "account_id": account.id,
        "date": prev_month,
        "category_id": savings_cat.id,
        "amount": -20_000,  # disponible anterior = 100_000 - 20_000 = 80_000
        "currency_id": 1,
    })

    result = initialize_month(db, target_month.year, target_month.month)
    assert result["created"] == 1

    new_budget = get_or_create_budget_month(db, savings_cat.id, target_month, 1)
    # accumulate: new_assigned = max(0, prev_assigned + prev_activity) = 80_000
    assert new_budget.assigned == 80_000


def test_initialize_month_skips_existing_rows():
    db = _make_session()
    _, _, expense_cat, _ = _seed_base(db)
    from dateutil.relativedelta import relativedelta

    prev_month = date.today().replace(day=1) - relativedelta(months=1)
    target_month = prev_month + relativedelta(months=1)

    prev_budget = get_or_create_budget_month(db, expense_cat.id, prev_month, 1)
    prev_budget.assigned = 250_000
    db.commit()

    # Target month already has a row
    get_or_create_budget_month(db, expense_cat.id, target_month, 1)
    db.commit()

    result = initialize_month(db, target_month.year, target_month.month)
    assert result["created"] == 0
    assert result["skipped"] == 1
