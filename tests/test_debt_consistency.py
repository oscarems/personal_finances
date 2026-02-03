from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from domain.debts.projection import project_debt_principal
from domain.debts.service import get_total_debt_principal_cop
from domain.debts.snapshot import build_debt_snapshots
from finance_app.api import reports
from finance_app.database import Base
from finance_app.models import (
    Currency,
    Debt,
    DebtSnapshotMonthly,
    ExchangeRate,
    RecurringTransaction,
)


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


def test_debt_totals_consistent_everywhere():
    db = _make_session()
    _seed_currencies(db)

    today = date.today().replace(day=1)
    debt = Debt(
        account_id=1,
        name="Prestamo",
        debt_type="credit_loan",
        currency_code="COP",
        original_amount=1000.0,
        current_balance=1000.0,
        start_date=today,
        is_active=True,
    )
    db.add(debt)
    db.commit()

    canonical_total = float(get_total_debt_principal_cop(db, today))

    net_worth = reports.get_net_worth(
        start_date=today.isoformat(),
        end_date=today.isoformat(),
        currency_id=1,
        db=db,
    )
    net_worth_liabilities = net_worth["monthly"][0]["liabilities"]

    summary = reports.get_debt_summary(currency_id=1, db=db)
    summary_total = summary["totals"]["total_debt"]

    assert abs(canonical_total - net_worth_liabilities) <= 0.01
    assert abs(canonical_total - summary_total) <= 0.01


def test_snapshot_first_day_rule():
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
    db.commit()

    build_debt_snapshots(db, start_month=date(2024, 2, 15), end_month=date(2024, 3, 20))

    snapshots = db.query(DebtSnapshotMonthly).all()
    assert snapshots
    assert all(snapshot.as_of_date.day == 1 for snapshot in snapshots)


def test_projection_uses_scheduled_payments():
    db = _make_session()
    _seed_currencies(db)

    debt = Debt(
        account_id=1,
        name="Prestamo",
        debt_type="credit_loan",
        currency_code="COP",
        original_amount=1000.0,
        current_balance=1000.0,
        category_id=10,
        start_date=date(2024, 1, 1),
        is_active=True,
    )
    db.add(debt)
    db.flush()

    recurring = RecurringTransaction(
        account_id=1,
        category_id=10,
        description="Pago prestamo",
        amount=100.0,
        currency_id=1,
        transaction_type="expense",
        frequency="monthly",
        interval=1,
        start_date=date(2024, 1, 5),
        is_active=True,
    )
    db.add(recurring)
    db.commit()

    timeline = project_debt_principal(db, date(2024, 1, 1), date(2024, 3, 1))
    jan_record = {r.debt_id: r for r in timeline[0]["records"]}[debt.id]
    feb_record = {r.debt_id: r for r in timeline[1]["records"]}[debt.id]
    mar_record = {r.debt_id: r for r in timeline[2]["records"]}[debt.id]

    assert float(jan_record.principal_original) == 1000.0
    assert float(feb_record.principal_original) == 900.0
    assert float(mar_record.principal_original) == 800.0


def test_multi_currency_base_cop():
    db = _make_session()
    _seed_currencies(db)

    debt = Debt(
        account_id=1,
        name="USD Loan",
        debt_type="credit_loan",
        currency_code="USD",
        original_amount=100.0,
        current_balance=100.0,
        start_date=date(2024, 1, 1),
        is_active=True,
    )
    db.add(debt)
    db.commit()

    total_cop = float(get_total_debt_principal_cop(db, date(2024, 1, 1)))
    assert total_cop == 400000.0
