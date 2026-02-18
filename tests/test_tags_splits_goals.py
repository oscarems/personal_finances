from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finance_app.database import Base
from finance_app.models import Account, Category, CategoryGroup, Currency, Goal, GoalContribution, Tag, Transaction
from finance_app.services.goal_service import calculate_goal_progress
from finance_app.services.transaction_allocation_service import get_category_allocations
from finance_app.services.transaction_service import create_transaction, create_transfer


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
    db.commit()
    return cop, usd, cat_a, cat_b


def test_normal_transaction_without_tags_or_splits_keeps_category_allocation():
    db = _make_session()
    _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=0)
    db.add(account)
    db.commit()

    tx = create_transaction(db, {
        "account_id": account.id,
        "date": date.today(),
        "category_id": 1,
        "amount": -100_000,
        "currency_id": 1,
        "memo": "Compra",
    })

    allocations = get_category_allocations(tx)
    assert len(allocations) == 1
    assert allocations[0]["category_id"] == 1
    assert allocations[0]["amount"] == -100_000


def test_transaction_with_tags_and_splits_assigns_data_and_preserves_total_amount():
    db = _make_session()
    _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=500_000)
    db.add(account)
    db.add_all([Tag(name="viaje"), Tag(name="familia")])
    db.commit()

    tx = create_transaction(db, {
        "account_id": account.id,
        "date": date.today(),
        "category_id": 1,
        "amount": -100_000,
        "currency_id": 1,
        "tag_ids": [1, 2],
        "splits": [
            {"category_id": 1, "amount": -60_000, "note": "super"},
            {"category_id": 2, "amount": -40_000, "note": "bus"},
        ],
    })

    assert account.balance == 400_000
    assert len(tx.tag_links) == 2
    allocations = get_category_allocations(tx)
    assert len(allocations) == 2
    assert round(sum(a["amount"] for a in allocations), 2) == -100_000


def test_transfer_cannot_have_splits():
    db = _make_session()
    _seed_base(db)
    from_account = Account(name="Cuenta 1", type="checking", currency_id=1, balance=100_000)
    to_account = Account(name="Cuenta 2", type="checking", currency_id=1, balance=0)
    db.add_all([from_account, to_account])
    db.commit()

    txs = create_transfer(db, {
        "from_account_id": from_account.id,
        "to_account_id": to_account.id,
        "date": date.today(),
        "amount": 30_000,
        "from_currency_id": 1,
        "to_currency_id": 1,
    })

    try:
        create_transaction(db, {
            "account_id": from_account.id,
            "date": date.today(),
            "amount": -10_000,
            "currency_id": 1,
            "transfer_account_id": to_account.id,
            "splits": [{"category_id": 1, "amount": -10_000}],
        })
        raised = False
    except ValueError:
        raised = True

    assert raised
    assert len(txs) == 2


def test_goal_linked_account_uses_increment_since_start_date_baseline():
    db = _make_session()
    _seed_base(db)
    account = Account(name="Ahorro meta", type="savings", currency_id=1, balance=350_000)
    db.add(account)
    db.commit()

    goal = Goal(
        name="Viaje",
        target_amount=500_000,
        target_date=date.today() + timedelta(days=180),
        currency_id=1,
        linked_account_id=account.id,
        start_date=date.today() - timedelta(days=30),
        start_amount=100_000,
        status="active",
    )
    db.add(goal)
    db.commit()

    metrics = calculate_goal_progress(db, goal)
    assert metrics["current_amount"] == 250_000
    assert metrics["required_per_month"] > 0


def test_goal_without_linked_account_uses_contributions():
    db = _make_session()
    _seed_base(db)
    goal = Goal(
        name="Laptop",
        target_amount=1_000,
        target_date=date.today() + timedelta(days=120),
        currency_id=2,
        linked_account_id=None,
        start_date=date.today() - timedelta(days=90),
        start_amount=0,
        status="active",
    )
    db.add(goal)
    db.commit()

    db.add_all([
        GoalContribution(goal_id=goal.id, date=date.today() - timedelta(days=60), amount=200, currency_id=2),
        GoalContribution(goal_id=goal.id, date=date.today() - timedelta(days=30), amount=250, currency_id=2),
    ])
    db.commit()

    metrics = calculate_goal_progress(db, goal, months_for_projection=3)
    assert metrics["current_amount"] == 450
    assert metrics["projected_achievement_date"] is not None
