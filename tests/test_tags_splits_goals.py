from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finance_app.database import Base
from finance_app.api.reports_pkg import spending as reports_spending
from finance_app.models import Account, Category, CategoryGroup, Currency, Debt, Goal, GoalContribution, Tag, Transaction
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


def test_transaction_with_tag_ids_ignores_tags_and_preserves_total_amount_with_splits():
    db = _make_session()
    _seed_base(db)
    # created_at is backdated to sidestep UTC-vs-local-clock edge cases around
    # midnight — transaction_affects_balance() requires tx_date >= created_at.
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=500_000, created_at=datetime(2020, 1, 1))
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
    assert len(tx.tag_links) == 0
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


def test_spending_by_tag_category_filter_uses_splits():
    db = _make_session()
    _seed_base(db)
    account = Account(name="Cuenta", type="checking", currency_id=1, balance=500_000)
    db.add(account)
    db.add_all([Tag(name="viaje"), Tag(name="hogar")])
    db.commit()

    create_transaction(db, {
        "account_id": account.id,
        "date": date.today(),
        "category_id": 1,
        "amount": -120_000,
        "currency_id": 1,
        "tag_ids": [1],
        "splits": [
            {"category_id": 1, "amount": -50_000},
            {"category_id": 2, "amount": -70_000},
        ],
    })

    payload = reports_spending.get_spending_by_tag(
        start_date=date.today().replace(day=1).isoformat(),
        end_date=date.today().isoformat(),
        currency_id=1,
        category_id=2,
        db=db,
    )

    untagged_row = next(row for row in payload["tags"] if row["tag"] == "(sin tag)")
    assert untagged_row["amount"] == 70_000


def test_transaction_can_be_associated_to_specific_debt_even_from_non_debt_account():
    # Uses credit_loan (not mortgage): mortgage balances are now derived purely from
    # original_amount/start_date/rate/term and are unaffected by individual transactions.
    db = _make_session()
    _seed_base(db)

    # created_at is backdated to sidestep UTC-vs-local-clock edge cases around
    # midnight — transaction_affects_balance() requires tx_date >= created_at.
    old_created_at = datetime(2020, 1, 1)
    payment_account = Account(name="Cuenta Nómina", type="checking", currency_id=1, balance=1_000_000, created_at=old_created_at)
    debt_account = Account(name="Cuenta Préstamo", type="credit_loan", currency_id=1, balance=0, created_at=old_created_at)
    db.add_all([payment_account, debt_account])
    db.commit()

    debt = Debt(
        account_id=debt_account.id,
        category_id=1,
        name="Préstamo Vehículo",
        debt_type="credit_loan",
        currency_code="COP",
        original_amount=500_000_000,
        current_balance=500_000_000,
        start_date=date.today(),
    )
    db.add(debt)
    db.commit()

    tx = create_transaction(db, {
        "account_id": payment_account.id,
        "date": date.today(),
        "category_id": 1,
        "debt_id": debt.id,
        "amount": -1_500_000,
        "currency_id": 1,
        "memo": "Cuota mensual préstamo",
    })

    db.refresh(debt)
    assert tx.debt_id == debt.id
    assert debt.current_balance == 498_500_000

