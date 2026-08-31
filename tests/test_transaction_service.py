from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finance_app.database import Base
from finance_app.models import Account, Category, CategoryGroup, Currency, ExchangeRate
from finance_app.services.budget_service import get_or_create_budget_month, recalculate_budget_available
from finance_app.services.transaction_service import (
    create_transaction,
    create_transfer,
    delete_transaction,
    update_transaction,
    is_budget_cover_adjustment,
    find_linked_transfer,
    TRANSFER_PAIR_IMPORT_PREFIX,
    create_reimbursement,
    reimbursement_remaining,
    get_monthly_activity,
)


def _make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_base(db):
    cop = Currency(id=1, code="COP", symbol="$", name="Peso", is_base=True, decimals=0)
    usd = Currency(id=2, code="USD", symbol="US$", name="Dollar", is_base=False, decimals=2)
    group = CategoryGroup(name="Gastos", sort_order=1, is_income=False)
    cat_a = Category(name="Mercado", category_group=group)
    cat_b = Category(name="Transporte", category_group=group)
    db.add_all([cop, usd, group, cat_a, cat_b])
    db.add(ExchangeRate(from_currency="USD", to_currency="COP", rate=4000.0, date=date(2024, 1, 1)))
    db.commit()
    return cop, usd, cat_a, cat_b


# ---------------------------------------------------------------------------
# Creación de transacción simple
# ---------------------------------------------------------------------------

def test_create_simple_transaction_updates_account_balance():
    db = _make_session()
    _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=100_000, created_at=datetime(2020, 1, 1))
    db.add(account)
    db.commit()

    tx = create_transaction(db, {
        "account_id": account.id,
        "date": date.today(),
        "category_id": 1,
        "amount": -30_000,
        "currency_id": 1,
        "memo": "Compra mercado",
    })

    assert tx.id is not None
    assert tx.amount == -30_000
    db.refresh(account)
    assert account.balance == 70_000


def test_create_transaction_missing_required_field_raises():
    db = _make_session()
    _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=0)
    db.add(account)
    db.commit()

    # No account_id → KeyError from data['account_id']
    with pytest.raises(KeyError):
        create_transaction(db, {
            "date": date.today(),
            "category_id": 1,
            "amount": -1000,
            "currency_id": 1,
        })

    # No amount → KeyError
    with pytest.raises(KeyError):
        create_transaction(db, {
            "account_id": account.id,
            "date": date.today(),
            "category_id": 1,
            "currency_id": 1,
        })

    # No currency_id → KeyError
    with pytest.raises(KeyError):
        create_transaction(db, {
            "account_id": account.id,
            "date": date.today(),
            "category_id": 1,
            "amount": -1000,
        })


# ---------------------------------------------------------------------------
# Splits
# ---------------------------------------------------------------------------

def test_splits_must_add_up_to_transaction_total():
    db = _make_session()
    _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=500_000, created_at=datetime(2020, 1, 1))
    db.add(account)
    db.commit()

    tx = create_transaction(db, {
        "account_id": account.id,
        "date": date.today(),
        "category_id": 1,
        "amount": -100_000,
        "currency_id": 1,
        "splits": [
            {"category_id": 1, "amount": -60_000},
            {"category_id": 2, "amount": -40_000},
        ],
    })

    assert len(tx.splits) == 2
    assert round(sum(s.amount for s in tx.splits), 2) == -100_000


def test_splits_that_do_not_sum_to_total_are_rejected():
    db = _make_session()
    _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=500_000)
    db.add(account)
    db.commit()

    with pytest.raises(ValueError):
        create_transaction(db, {
            "account_id": account.id,
            "date": date.today(),
            "category_id": 1,
            "amount": -100_000,
            "currency_id": 1,
            "splits": [
                {"category_id": 1, "amount": -60_000},
                {"category_id": 2, "amount": -30_000},  # sums to -90_000, not -100_000
            ],
        })


def test_splits_with_invalid_category_are_rejected():
    db = _make_session()
    _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=500_000)
    db.add(account)
    db.commit()

    with pytest.raises(ValueError):
        create_transaction(db, {
            "account_id": account.id,
            "date": date.today(),
            "category_id": 1,
            "amount": -100_000,
            "currency_id": 1,
            "splits": [
                {"category_id": 999, "amount": -100_000},
            ],
        })


# ---------------------------------------------------------------------------
# Transferencias
# ---------------------------------------------------------------------------

def test_transfer_creates_two_linked_transactions_with_opposite_signs():
    db = _make_session()
    _seed_base(db)
    from_account = Account(name="Origen", type="checking", currency_id=1, balance=200_000, created_at=datetime(2020, 1, 1))
    to_account = Account(name="Destino", type="savings", currency_id=1, balance=0, created_at=datetime(2020, 1, 1))
    db.add_all([from_account, to_account])
    db.commit()

    from_tx, to_tx = create_transfer(db, {
        "from_account_id": from_account.id,
        "to_account_id": to_account.id,
        "date": date.today(),
        "amount": 50_000,
        "from_currency_id": 1,
        "to_currency_id": 1,
    })

    assert from_tx.amount == -50_000
    assert to_tx.amount == 50_000
    assert from_tx.transfer_account_id == to_account.id
    assert to_tx.transfer_account_id == from_account.id

    db.refresh(from_account)
    db.refresh(to_account)
    assert from_account.balance == 150_000
    assert to_account.balance == 50_000


def test_transfer_same_account_raises():
    db = _make_session()
    _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=100_000)
    db.add(account)
    db.commit()

    with pytest.raises(ValueError):
        create_transfer(db, {
            "from_account_id": account.id,
            "to_account_id": account.id,
            "date": date.today(),
            "amount": 10_000,
            "from_currency_id": 1,
            "to_currency_id": 1,
        })


def test_delete_transfer_removes_both_transactions_and_reverts_balances():
    db = _make_session()
    _seed_base(db)
    from_account = Account(name="Origen", type="checking", currency_id=1, balance=200_000, created_at=datetime(2020, 1, 1))
    to_account = Account(name="Destino", type="savings", currency_id=1, balance=0, created_at=datetime(2020, 1, 1))
    db.add_all([from_account, to_account])
    db.commit()

    from_tx, to_tx = create_transfer(db, {
        "from_account_id": from_account.id,
        "to_account_id": to_account.id,
        "date": date.today(),
        "amount": 50_000,
        "from_currency_id": 1,
        "to_currency_id": 1,
    })

    delete_transaction(db, from_tx.id)

    db.refresh(from_account)
    db.refresh(to_account)
    assert from_account.balance == 200_000
    assert to_account.balance == 0


# ---------------------------------------------------------------------------
# Actualización del disponible de presupuesto
# ---------------------------------------------------------------------------

def test_budget_available_updates_when_transaction_created_updated_deleted():
    db = _make_session()
    _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=1_000_000, created_at=datetime(2020, 1, 1))
    db.add(account)
    db.commit()

    month = date.today().replace(day=1)
    budget = get_or_create_budget_month(db, category_id=1, month_date=month, currency_id=1)
    budget.assigned = 200_000
    db.commit()

    tx = create_transaction(db, {
        "account_id": account.id,
        "date": date.today(),
        "category_id": 1,
        "amount": -50_000,
        "currency_id": 1,
    })

    recalculate_budget_available(db, budget)
    db.commit()
    assert budget.activity == -50_000
    assert budget.available == 150_000

    update_transaction(db, tx.id, {"amount": -80_000, "currency_id": 1})

    recalculate_budget_available(db, budget)
    db.commit()
    assert budget.activity == -80_000
    assert budget.available == 120_000

    delete_transaction(db, tx.id)

    recalculate_budget_available(db, budget)
    db.commit()
    assert budget.activity == 0
    assert budget.available == 200_000


# ---------------------------------------------------------------------------
# Moneda distinta a la de la cuenta
# ---------------------------------------------------------------------------

def test_transaction_currency_different_from_account_is_converted():
    db = _make_session()
    _seed_base(db)
    # Cuenta en COP, transacción registrada en USD
    account = Account(name="Cuenta COP", type="checking", currency_id=1, balance=0, created_at=datetime(2020, 1, 1))
    db.add(account)
    db.commit()

    tx = create_transaction(db, {
        "account_id": account.id,
        "date": date(2024, 1, 1),
        "category_id": 1,
        "amount": -10,  # -10 USD
        "currency_id": 2,  # USD
    })

    # amount stored in the account's currency (COP), original_amount preserved in USD
    assert tx.currency_id == 1
    assert tx.amount == -40_000  # -10 USD * 4000
    assert tx.original_amount == -10
    assert tx.original_currency_id == 2

    db.refresh(account)
    assert account.balance == -40_000


# ---------------------------------------------------------------------------
# Splits → actividad de presupuesto
# ---------------------------------------------------------------------------

def test_split_transaction_activity_is_allocated_per_category():
    db = _make_session()
    _, _, cat_a, cat_b = _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=500_000, created_at=datetime(2020, 1, 1))
    db.add(account)
    db.commit()

    month = date.today().replace(day=1)
    budget_a = get_or_create_budget_month(db, cat_a.id, month, 1)
    budget_a.assigned = 100_000
    budget_b = get_or_create_budget_month(db, cat_b.id, month, 1)
    budget_b.assigned = 100_000
    db.commit()

    create_transaction(db, {
        "account_id": account.id,
        "date": date.today(),
        "category_id": cat_a.id,  # header alone would wrongly give A the full -100k
        "amount": -100_000,
        "currency_id": 1,
        "splits": [
            {"category_id": cat_a.id, "amount": -60_000},
            {"category_id": cat_b.id, "amount": -40_000},
        ],
    })

    recalculate_budget_available(db, budget_a)
    recalculate_budget_available(db, budget_b)
    db.commit()

    assert budget_a.activity == -60_000
    assert budget_b.activity == -40_000
    assert budget_a.available == 40_000
    assert budget_b.available == 60_000


# ---------------------------------------------------------------------------
# Préstamo: reverse restaura principal, no el pago completo
# ---------------------------------------------------------------------------

def test_loan_payment_reverse_restores_principal_not_full_payment():
    from finance_app.models import Debt, DebtPayment
    from finance_app.services.transaction_service import delete_transaction

    db = _make_session()
    _seed_base(db)
    account = Account(
        name="Prestamo",
        type="credit_loan",
        currency_id=1,
        balance=0,
        created_at=datetime(2020, 1, 1),
    )
    db.add(account)
    db.commit()

    debt = Debt(
        account_id=account.id,
        name="Prestamo auto",
        debt_type="credit_loan",
        currency_code="COP",
        original_amount=100_000,
        current_balance=100_000,
        interest_rate=24.0,  # annual %
        start_date=date.today(),
        is_active=True,
    )
    db.add(debt)
    db.commit()

    tx = create_transaction(db, {
        "account_id": account.id,
        "date": date.today(),
        "amount": -5_000,
        "currency_id": 1,
        "debt_id": debt.id,
    })

    db.refresh(debt)
    payment = db.query(DebtPayment).filter_by(transaction_id=tx.id).one()
    assert payment.principal is not None
    assert payment.principal < payment.amount
    balance_after_pay = debt.current_balance
    assert balance_after_pay == pytest.approx(100_000 - payment.principal)

    delete_transaction(db, tx.id)
    db.refresh(debt)
    assert debt.current_balance == pytest.approx(100_000)


def test_estimate_period_interest_prefers_monthly_interest_rate():
    from finance_app.models import Debt
    from finance_app.services.transaction_service import _estimate_period_interest

    debt = Debt(
        name="x",
        debt_type="credit_loan",
        current_balance=100_000,
        monthly_interest_rate=1.9,  # 1.9%/mo
        interest_rate=None,
        annual_interest_rate=None,
    )
    interest = _estimate_period_interest(debt, 10_000)
    assert interest == pytest.approx(1_900.0)


# ---------------------------------------------------------------------------
# Cover adjustments vs account.balance (BUG-002)
# ---------------------------------------------------------------------------

def test_create_and_delete_cover_leaves_account_balance_unchanged():
    """Cover create does not touch balance; delete must also leave it invariant."""
    from finance_app.api.budgets import CoverOverspendingRequest, cover_overspending
    from finance_app.models import Transaction

    db = _make_session()
    _, _, cat_a, cat_b = _seed_base(db)
    budget_acct = Account(
        name="Presupuesto COP",
        type="checking",
        currency_id=1,
        balance=800_000,
        is_budget=True,
        is_closed=False,
        created_at=datetime(2020, 1, 1),
    )
    db.add(budget_acct)
    db.commit()

    month = date.today().replace(day=1)
    get_or_create_budget_month(db, cat_a.id, month, 1).assigned = 200_000
    get_or_create_budget_month(db, cat_b.id, month, 1).assigned = 100_000
    db.commit()

    balance_before = budget_acct.balance

    cover_overspending(
        CoverOverspendingRequest(
            source_category_id=cat_a.id,
            target_category_id=cat_b.id,
            amount=25_000,
            currency_code="COP",
            month=month,
        ),
        db,
    )

    db.refresh(budget_acct)
    assert budget_acct.balance == balance_before

    covers = db.query(Transaction).filter(Transaction.is_adjustment.is_(True)).all()
    assert len(covers) == 2
    assert all(is_budget_cover_adjustment(t) for t in covers)

    for tx in list(covers):
        delete_transaction(db, tx.id)

    db.refresh(budget_acct)
    assert budget_acct.balance == balance_before
    assert db.query(Transaction).filter(Transaction.is_adjustment.is_(True)).count() == 0


# ---------------------------------------------------------------------------
# BUG-026 — transfer pair matching
# ---------------------------------------------------------------------------

def test_create_transfer_stamps_shared_pair_import_id():
    db = _make_session()
    _seed_base(db)
    from_account = Account(name="Origen", type="checking", currency_id=1, balance=200_000, created_at=datetime(2020, 1, 1))
    to_account = Account(name="Destino", type="savings", currency_id=1, balance=0, created_at=datetime(2020, 1, 1))
    db.add_all([from_account, to_account])
    db.commit()

    from_tx, to_tx = create_transfer(db, {
        "from_account_id": from_account.id,
        "to_account_id": to_account.id,
        "date": date.today(),
        "amount": 50_000,
        "from_currency_id": 1,
        "to_currency_id": 1,
    })

    assert from_tx.import_id and from_tx.import_id.startswith(TRANSFER_PAIR_IMPORT_PREFIX)
    assert from_tx.import_id == to_tx.import_id
    assert find_linked_transfer(db, from_tx).id == to_tx.id
    assert find_linked_transfer(db, to_tx).id == from_tx.id


def test_delete_transfer_matches_by_amount_when_same_day_same_accounts():
    """Two same-day transfers between the same accounts must not cross-delete."""
    from finance_app.models import Transaction

    db = _make_session()
    _seed_base(db)
    from_account = Account(name="Origen", type="checking", currency_id=1, balance=500_000, created_at=datetime(2020, 1, 1))
    to_account = Account(name="Destino", type="savings", currency_id=1, balance=0, created_at=datetime(2020, 1, 1))
    db.add_all([from_account, to_account])
    db.commit()

    day = date.today()
    a_from, a_to = create_transfer(db, {
        "from_account_id": from_account.id,
        "to_account_id": to_account.id,
        "date": day,
        "amount": 10_000,
        "from_currency_id": 1,
        "to_currency_id": 1,
    })
    b_from, b_to = create_transfer(db, {
        "from_account_id": from_account.id,
        "to_account_id": to_account.id,
        "date": day,
        "amount": 77_000,
        "from_currency_id": 1,
        "to_currency_id": 1,
    })

    # Simulate legacy transfers without pair import_id
    for tx in (a_from, a_to, b_from, b_to):
        tx.import_id = None
    db.commit()

    delete_transaction(db, a_from.id)

    remaining = {t.id for t in db.query(Transaction).all()}
    assert a_from.id not in remaining
    assert a_to.id not in remaining
    assert b_from.id in remaining
    assert b_to.id in remaining

    db.refresh(from_account)
    db.refresh(to_account)
    assert from_account.balance == 500_000 - 77_000
    assert to_account.balance == 77_000


# ---------------------------------------------------------------------------
# BUG-027 — memo-only patch must not regenerate DebtPayment
# ---------------------------------------------------------------------------

def test_update_memo_only_does_not_regenerate_debt_payment_interest():
    from finance_app.models import Debt, DebtPayment

    db = _make_session()
    _seed_base(db)
    account = Account(
        name="Prestamo",
        type="credit_loan",
        currency_id=1,
        balance=0,
        created_at=datetime(2020, 1, 1),
    )
    db.add(account)
    db.commit()

    debt = Debt(
        account_id=account.id,
        name="Préstamo",
        debt_type="credit_loan",
        currency_code="COP",
        original_amount=100_000,
        current_balance=100_000,
        interest_rate=24.0,
        start_date=date.today(),
        is_active=True,
    )
    db.add(debt)
    db.commit()

    tx = create_transaction(db, {
        "account_id": account.id,
        "date": date.today(),
        "amount": -5_000,
        "currency_id": 1,
        "debt_id": debt.id,
        "memo": "Cuota original",
    })

    payment = db.query(DebtPayment).filter_by(transaction_id=tx.id).one()
    payment_id = payment.id
    interest_before = payment.interest
    principal_before = payment.principal
    balance_before = debt.current_balance

    update_transaction(db, tx.id, {"memo": "Cuota editada (solo memo)"})

    db.refresh(debt)
    payment_after = db.query(DebtPayment).filter_by(transaction_id=tx.id).one()
    assert payment_after.id == payment_id
    assert payment_after.interest == interest_before
    assert payment_after.principal == principal_before
    assert debt.current_balance == balance_before
    db.refresh(tx)
    assert tx.memo == "Cuota editada (solo memo)"


# ---------------------------------------------------------------------------
# BUG-029 — bulk category update recalculates budget
# ---------------------------------------------------------------------------

def test_bulk_category_update_recalculates_budget_available():
    from finance_app.api.transactions import BulkUpdateBody, bulk_update_transactions

    db = _make_session()
    _, _, cat_a, cat_b = _seed_base(db)
    account = Account(
        name="Cuenta",
        type="checking",
        currency_id=1,
        balance=1_000_000,
        created_at=datetime(2020, 1, 1),
    )
    db.add(account)
    db.commit()

    month = date.today().replace(day=1)
    budget_a = get_or_create_budget_month(db, cat_a.id, month, 1)
    budget_a.assigned = 200_000
    budget_b = get_or_create_budget_month(db, cat_b.id, month, 1)
    budget_b.assigned = 200_000
    db.commit()

    tx = create_transaction(db, {
        "account_id": account.id,
        "date": month,
        "category_id": cat_a.id,
        "amount": -40_000,
        "currency_id": 1,
    })

    recalculate_budget_available(db, budget_a)
    recalculate_budget_available(db, budget_b)
    db.commit()
    assert budget_a.available == 160_000
    assert budget_b.available == 200_000

    bulk_update_transactions(
        BulkUpdateBody(ids=[tx.id], category_id=cat_b.id),
        db,
    )

    db.refresh(budget_a)
    db.refresh(budget_b)
    recalculate_budget_available(db, budget_a)
    recalculate_budget_available(db, budget_b)
    assert budget_a.activity == 0
    assert budget_a.available == 200_000
    assert budget_b.activity == -40_000
    assert budget_b.available == 160_000


# ---------------------------------------------------------------------------
# Reembolsos y préstamos personales
# ---------------------------------------------------------------------------

def test_reimbursement_nets_category_activity_and_is_not_income():
    db = _make_session()
    _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=1_000_000, created_at=datetime(2020, 1, 1))
    db.add(account)
    db.commit()
    today = date.today()

    expense = create_transaction(db, {
        "account_id": account.id,
        "date": today,
        "category_id": 1,
        "amount": 100_000,
        "currency_id": 1,
        "type": "expense",
        "payee_name": "Hotel Cartagena",
    })
    rebate = create_reimbursement(db, expense.id, {
        "date": today,
        "amount": 40_000,
        "account_id": account.id,
        "payee_name": "Camilo",
    })

    assert rebate.amount == 40_000
    assert rebate.kind == "reimbursement"
    assert rebate.related_transaction_id == expense.id
    assert rebate.category_id == expense.category_id
    assert reimbursement_remaining(db, expense) == 60_000

    activity = get_monthly_activity(db, 1, today.month, today.year, 1)
    assert activity == -60_000

    from finance_app.services.budget_service import build_income_transactions_query
    start = today.replace(day=1)
    month_end = date(today.year + (1 if today.month == 12 else 0), 1 if today.month == 12 else today.month + 1, 1)
    income_ids = {t.id for t in build_income_transactions_query(db, start, month_end).all()}
    assert rebate.id not in income_ids


def test_reimbursement_cannot_exceed_remaining():
    db = _make_session()
    _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=500_000, created_at=datetime(2020, 1, 1))
    db.add(account)
    db.commit()
    today = date.today()

    expense = create_transaction(db, {
        "account_id": account.id,
        "date": today,
        "category_id": 1,
        "amount": 50_000,
        "currency_id": 1,
        "type": "expense",
    })
    create_reimbursement(db, expense.id, {"date": today, "amount": 30_000, "account_id": account.id})

    with pytest.raises(ValueError, match="pendiente"):
        create_reimbursement(db, expense.id, {"date": today, "amount": 30_000, "account_id": account.id})


def test_loan_and_repayment():
    db = _make_session()
    _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=500_000, created_at=datetime(2020, 1, 1))
    db.add(account)
    db.commit()
    today = date.today()

    loan = create_transaction(db, {
        "account_id": account.id,
        "date": today,
        "category_id": 1,
        "amount": 80_000,
        "currency_id": 1,
        "type": "loan",
        "payee_name": "Ana",
    })
    assert loan.kind == "loan"
    assert loan.amount == -80_000

    repayment = create_reimbursement(db, loan.id, {
        "date": today,
        "amount": 80_000,
        "account_id": account.id,
        "payee_name": "Ana",
    })
    assert repayment.kind == "loan_repayment"
    assert repayment.amount == 80_000
    assert reimbursement_remaining(db, loan) == 0

    db.refresh(account)
    assert account.balance == 500_000


def test_delete_original_unlinks_reimbursement():
    db = _make_session()
    _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=200_000, created_at=datetime(2020, 1, 1))
    db.add(account)
    db.commit()
    today = date.today()

    expense = create_transaction(db, {
        "account_id": account.id,
        "date": today,
        "category_id": 1,
        "amount": 20_000,
        "currency_id": 1,
        "type": "expense",
    })
    rebate = create_reimbursement(db, expense.id, {
        "date": today,
        "amount": 5_000,
        "account_id": account.id,
    })
    delete_transaction(db, expense.id)
    db.refresh(rebate)
    assert rebate.related_transaction_id is None
