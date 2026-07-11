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
