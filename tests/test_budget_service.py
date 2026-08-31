from datetime import date, datetime

import pytest
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
from finance_app.services.transaction_service import create_transaction, create_reimbursement

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


def test_recalculate_income_category_tracks_activity_but_available_stays_zero():
    """Income cats: activity = real inflows; available never accumulates."""
    db = _make_session()
    cop, _, _, _ = _seed_base(db)
    income_group = CategoryGroup(name="Ingresos", sort_order=0, is_income=True)
    salary = Category(name="Salario", category_group=income_group, rollover_type="reset")
    account = Account(
        name="Cuenta", type="checking", currency_id=cop.id,
        balance=5_000_000, created_at=datetime(2020, 1, 1),
    )
    db.add_all([income_group, salary, account])
    db.commit()

    month = date.today().replace(day=1)
    budget = get_or_create_budget_month(db, salary.id, month, cop.id)
    budget.assigned = 4_000_000  # planned
    db.commit()

    create_transaction(db, {
        "account_id": account.id,
        "date": date.today(),
        "category_id": salary.id,
        "amount": 3_500_000,
        "currency_id": cop.id,
    })

    recalculate_budget_available(db, budget)
    db.commit()

    assert budget.activity == 3_500_000
    assert budget.available == 0.0

    from finance_app.services.budget_service import get_month_budget
    data = get_month_budget(db, month, "COP")
    assert data["totals"]["income"] == 3_500_000


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
    # disponible = prev.disponible + asignado + activity
    assert new_budget.assigned == 100_000  # hereda asignado del mes anterior
    assert new_budget.initial_overridden is False
    assert (new_budget.initial_amount or 0.0) == 80_000
    assert new_budget.available == 80_000 + 100_000


# ---------------------------------------------------------------------------
# BUG-008 — initialize_month vs get_or_create_budget_month parity (accumulate)
# ---------------------------------------------------------------------------

def test_initialize_and_get_or_create_accumulate_parity():
    """Both create paths must yield the same assigned / initial / available."""
    from dateutil.relativedelta import relativedelta
    from finance_app.models import BudgetMonth

    def _seed_prev(db, savings_cat, account, prev_month):
        prev = get_or_create_budget_month(db, savings_cat.id, prev_month, 1)
        prev.assigned = 100_000
        db.commit()
        create_transaction(db, {
            "account_id": account.id,
            "date": prev_month,
            "category_id": savings_cat.id,
            "amount": -20_000,
            "currency_id": 1,
        })
        recalculate_budget_available(db, prev)
        db.commit()
        return prev

    # Path A: initialize_month
    db_a = _make_session()
    _, _, _, savings_a = _seed_base(db_a)
    acct_a = Account(name="A", type="savings", currency_id=1, balance=1_000_000, created_at=datetime(2020, 1, 1))
    db_a.add(acct_a)
    db_a.commit()
    prev_m = date(2024, 6, 1)
    target_m = date(2024, 7, 1)
    _seed_prev(db_a, savings_a, acct_a, prev_m)
    initialize_month(db_a, target_m.year, target_m.month)
    via_init = db_a.query(BudgetMonth).filter_by(
        category_id=savings_a.id, month=target_m, currency_id=1
    ).one()

    # Path B: get_or_create + recalculate (same prior state, independent DB)
    db_b = _make_session()
    _, _, _, savings_b = _seed_base(db_b)
    acct_b = Account(name="B", type="savings", currency_id=1, balance=1_000_000, created_at=datetime(2020, 1, 1))
    db_b.add(acct_b)
    db_b.commit()
    _seed_prev(db_b, savings_b, acct_b, prev_m)
    via_goc = get_or_create_budget_month(db_b, savings_b.id, target_m, 1)
    recalculate_budget_available(db_b, via_goc)
    db_b.commit()

    assert via_init.assigned == via_goc.assigned == 100_000
    assert (via_init.initial_amount or 0.0) == (via_goc.initial_amount or 0.0) == 80_000
    assert via_init.available == via_goc.available == 180_000
    assert via_init.initial_overridden is False
    assert via_goc.initial_overridden is False


# ---------------------------------------------------------------------------
# BUG-009 — recalculate_month multi-currency activity
# ---------------------------------------------------------------------------

def test_recalculate_month_does_not_inflate_multi_currency_activity():
    from finance_app.services.budget_service import recalculate_month
    from finance_app.models import BudgetMonth

    db = _make_session()
    _, _, expense_cat, _ = _seed_base(db)
    acct_cop = Account(name="COP", type="checking", currency_id=1, balance=1_000_000, created_at=datetime(2020, 1, 1))
    acct_usd = Account(name="USD", type="checking", currency_id=2, balance=1_000, created_at=datetime(2020, 1, 1))
    db.add_all([acct_cop, acct_usd])
    db.commit()

    prev_month = date(2024, 5, 1)
    month = date(2024, 6, 1)

    for m in (prev_month, month):
        for cur_id, assigned in ((1, 200_000), (2, 50.0)):
            b = get_or_create_budget_month(db, expense_cat.id, m, cur_id)
            b.assigned = assigned
    db.commit()

    create_transaction(db, {
        "account_id": acct_cop.id,
        "date": month,
        "category_id": expense_cat.id,
        "amount": -40_000,
        "currency_id": 1,
    })
    create_transaction(db, {
        "account_id": acct_usd.id,
        "date": month,
        "category_id": expense_cat.id,
        "amount": -10.0,
        "currency_id": 2,
    })

    recalculate_month(db, month)

    row_cop = db.query(BudgetMonth).filter_by(
        category_id=expense_cat.id, month=month, currency_id=1
    ).one()
    row_usd = db.query(BudgetMonth).filter_by(
        category_id=expense_cat.id, month=month, currency_id=2
    ).one()

    # Each currency row only counts its own activity (no cross-currency inflate)
    assert row_cop.activity == -40_000
    assert row_usd.activity == -10.0
    assert row_cop.available == 200_000 - 40_000
    assert row_usd.available == 50.0 - 10.0


# ---------------------------------------------------------------------------
# BUG-023 — signed group activity totals
# ---------------------------------------------------------------------------

def test_group_activity_totals_use_signed_activity():
    from finance_app.services.budget_service import get_month_budget

    db = _make_session()
    _, _, expense_cat, _ = _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=1_000_000, created_at=datetime(2020, 1, 1))
    db.add(account)
    db.commit()

    month = date(2024, 8, 1)
    budget = get_or_create_budget_month(db, expense_cat.id, month, 1)
    budget.assigned = 100_000
    db.commit()

    create_transaction(db, {
        "account_id": account.id,
        "date": month,
        "category_id": expense_cat.id,
        "amount": -30_000,
        "currency_id": 1,
    })

    data = get_month_budget(db, month, "COP")
    assert data["totals"]["activity"] == -30_000  # signed, not abs()


# ---------------------------------------------------------------------------
# BUG-024 — move_to_next_month carry-over
# ---------------------------------------------------------------------------

def test_move_to_next_month_carries_accumulate_available():
    from finance_app.services.budget_service import move_to_next_month
    from finance_app.models import BudgetMonth

    db = _make_session()
    _, _, expense_cat, savings_cat = _seed_base(db)
    account = Account(name="Cuenta", type="savings", currency_id=1, balance=1_000_000, created_at=datetime(2020, 1, 1))
    db.add(account)
    db.commit()

    current = date(2024, 3, 1)
    nxt = date(2024, 4, 1)

    sav = get_or_create_budget_month(db, savings_cat.id, current, 1)
    sav.assigned = 100_000
    exp = get_or_create_budget_month(db, expense_cat.id, current, 1)
    exp.assigned = 50_000
    db.commit()

    create_transaction(db, {
        "account_id": account.id,
        "date": current,
        "category_id": savings_cat.id,
        "amount": -20_000,
        "currency_id": 1,
    })

    move_to_next_month(db, current, 1)

    next_sav = db.query(BudgetMonth).filter_by(
        category_id=savings_cat.id, month=nxt, currency_id=1
    ).one()
    next_exp = db.query(BudgetMonth).filter_by(
        category_id=expense_cat.id, month=nxt, currency_id=1
    ).one()

    # accumulate: available = prev.available(80k) + assigned(100k) + 0
    assert next_sav.assigned == 100_000
    assert (next_sav.initial_amount or 0.0) == 80_000
    assert next_sav.available == 180_000

    # reset: no rollover of leftover available
    assert next_exp.assigned == 50_000
    assert next_exp.available == 50_000
    assert (next_exp.initial_amount or 0.0) == 0.0

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


# ---------------------------------------------------------------------------
# Cover overspending (BUG-001 / BUG-003)
# ---------------------------------------------------------------------------

def test_cover_overspending_moves_available_source_down_target_up():
    """After cover, source available decreases and target available increases.

    Activity stays real spending only (cover adjustments excluded from activity).
    """
    from finance_app.api.budgets import CoverOverspendingRequest, cover_overspending
    from finance_app.models import Transaction

    db = _make_session()
    _, _, expense_cat, savings_cat = _seed_base(db)
    budget_acct = Account(
        name="Presupuesto COP",
        type="checking",
        currency_id=1,
        balance=2_000_000,
        is_budget=True,
        is_closed=False,
        created_at=datetime(2020, 1, 1),
    )
    db.add(budget_acct)
    db.commit()

    month = date.today().replace(day=1)
    source_budget = get_or_create_budget_month(db, savings_cat.id, month, 1)
    source_budget.assigned = 200_000
    target_budget = get_or_create_budget_month(db, expense_cat.id, month, 1)
    target_budget.assigned = 100_000
    db.commit()

    # Overspend on target: available would be -50_000 without cover
    create_transaction(db, {
        "account_id": budget_acct.id,
        "date": month,
        "category_id": expense_cat.id,
        "amount": -150_000,
        "currency_id": 1,
    })

    recalculate_budget_available(db, source_budget)
    recalculate_budget_available(db, target_budget)
    db.commit()
    assert source_budget.available == 200_000
    assert target_budget.available == -50_000
    assert target_budget.activity == -150_000

    cover_overspending(
        CoverOverspendingRequest(
            source_category_id=savings_cat.id,
            target_category_id=expense_cat.id,
            amount=50_000,
            currency_code="COP",
            month=month,
        ),
        db,
    )

    db.refresh(source_budget)
    db.refresh(target_budget)
    recalculate_budget_available(db, source_budget)
    recalculate_budget_available(db, target_budget)

    assert source_budget.available == 150_000  # gave 50k
    assert target_budget.available == 0  # received 50k cover
    assert target_budget.activity == -150_000  # spending unchanged
    assert source_budget.activity == 0

    covers = db.query(Transaction).filter(Transaction.is_adjustment.is_(True)).all()
    assert len(covers) == 2


def test_update_cover_rollback_keeps_original_pair(monkeypatch):
    """If recreate fails after delete+flush, rollback restores the original pair."""
    from fastapi import HTTPException
    import finance_app.api.budgets as budgets_api
    from finance_app.api.budgets import (
        CoverOverspendingRequest,
        UpdateCoverOverspendingRequest,
        cover_overspending,
        update_cover_overspending,
    )
    from finance_app.models import Transaction

    db = _make_session()
    _, _, expense_cat, savings_cat = _seed_base(db)
    budget_acct = Account(
        name="Presupuesto COP",
        type="checking",
        currency_id=1,
        balance=1_000_000,
        is_budget=True,
        is_closed=False,
        created_at=datetime(2020, 1, 1),
    )
    db.add(budget_acct)
    db.commit()

    month = date.today().replace(day=1)
    get_or_create_budget_month(db, savings_cat.id, month, 1).assigned = 200_000
    get_or_create_budget_month(db, expense_cat.id, month, 1).assigned = 100_000
    db.commit()

    cover_overspending(
        CoverOverspendingRequest(
            source_category_id=savings_cat.id,
            target_category_id=expense_cat.id,
            amount=40_000,
            currency_code="COP",
            month=month,
        ),
        db,
    )

    covers_before = (
        db.query(Transaction)
        .filter(Transaction.is_adjustment.is_(True))
        .order_by(Transaction.id)
        .all()
    )
    assert len(covers_before) == 2
    source_tx = next(t for t in covers_before if t.amount < 0)
    before_ids = {t.id for t in covers_before}
    before_amounts = {(t.category_id, t.amount, t.memo) for t in covers_before}

    def _boom(*_args, **_kwargs):
        raise HTTPException(status_code=400, detail="No budget account found for currency COP")

    monkeypatch.setattr(budgets_api, "_create_cover_overspending_pair", _boom)

    with pytest.raises(HTTPException):
        update_cover_overspending(
            source_tx.id,
            UpdateCoverOverspendingRequest(
                counterpart_category_id=expense_cat.id,
                amount=99_000,
                currency_code="COP",
            ),
            db,
        )

    covers_after = (
        db.query(Transaction)
        .filter(Transaction.is_adjustment.is_(True))
        .order_by(Transaction.id)
        .all()
    )
    assert {t.id for t in covers_after} == before_ids
    assert {(t.category_id, t.amount, t.memo) for t in covers_after} == before_amounts


def test_reimbursement_does_not_change_assigned_and_restores_available_and_rta():
    """Devolución on an expense category: assigned stays put; gastado nets; RTA unchanged."""
    db = _make_session()
    _, _, expense_cat, _ = _seed_base(db)
    account = Account(
        name="Cuenta",
        type="checking",
        currency_id=1,
        balance=1_000_000,
        is_budget=True,
        created_at=datetime(2020, 1, 1),
    )
    db.add(account)
    db.commit()

    month = date.today().replace(day=1)
    budget = get_or_create_budget_month(db, expense_cat.id, month, 1)
    budget.assigned = 200_000
    db.commit()
    recalculate_budget_available(db, budget)
    db.commit()

    rta_before = calculate_ready_to_assign(db, month, 1)

    expense = create_transaction(db, {
        "account_id": account.id,
        "date": date.today(),
        "category_id": expense_cat.id,
        "amount": -80_000,
        "currency_id": 1,
        "type": "expense",
        "payee_name": "Hotel",
    })
    recalculate_budget_available(db, budget)
    db.commit()
    assert budget.assigned == 200_000
    assert budget.activity == -80_000
    assert budget.available == 120_000

    rta_after_spend = calculate_ready_to_assign(db, month, 1)
    assert rta_after_spend == pytest.approx(rta_before, abs=0.01)

    create_reimbursement(db, expense.id, {
        "date": date.today(),
        "amount": 30_000,
        "account_id": account.id,
        "payee_name": "Camilo",
    })
    recalculate_budget_available(db, budget)
    db.commit()

    assert budget.assigned == 200_000
    assert budget.activity == -50_000
    assert budget.available == 150_000

    rta_after_reimburse = calculate_ready_to_assign(db, month, 1)
    assert rta_after_reimburse == pytest.approx(rta_before, abs=0.01)
