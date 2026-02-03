from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finance_app.database import Base
from finance_app.api import reports
from finance_app.models import Currency, ExchangeRate, WealthAsset, Debt, DebtPayment, Transaction


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


def test_net_worth_includes_only_bienes_and_inversiones_with_forward_fill():
    db = _make_session()
    _seed_currencies(db)

    asset_bien = WealthAsset(
        name="Casa",
        asset_class="inmueble",
        value=1000.0,
        currency_id=1,
        as_of_date=date(2024, 1, 1),
    )
    asset_inversion = WealthAsset(
        name="Fondo",
        asset_class="inversion",
        value=500.0,
        currency_id=1,
        as_of_date=date(2024, 1, 1),
    )
    asset_bien_activo = WealthAsset(
        name="Carro",
        asset_class="activo",
        value=200.0,
        currency_id=1,
        as_of_date=date(2024, 1, 1),
    )
    asset_excluded = WealthAsset(
        name="Efectivo",
        asset_class="cash",
        value=999.0,
        currency_id=1,
        as_of_date=date(2024, 1, 1),
    )
    db.add_all([asset_bien, asset_inversion, asset_bien_activo, asset_excluded])
    db.flush()

    tx_feb = Transaction(
        account_id=1,
        date=date(2024, 2, 15),
        amount=-200.0,
        currency_id=1,
        original_amount=-200.0,
        original_currency_id=1,
        investment_asset_id=asset_inversion.id,
    )
    tx_mar = Transaction(
        account_id=1,
        date=date(2024, 3, 10),
        amount=100.0,
        currency_id=1,
        original_amount=100.0,
        original_currency_id=1,
        investment_asset_id=asset_inversion.id,
    )
    db.add_all([tx_feb, tx_mar])

    debt = Debt(
        account_id=1,
        name="Tarjeta",
        debt_type="credit_card",
        currency_code="COP",
        original_amount=300.0,
        current_balance=300.0,
        start_date=date(2024, 1, 1),
        is_active=True,
    )
    db.add(debt)
    db.commit()

    result = reports.get_net_worth(
        start_date="2024-01-01",
        end_date="2024-03-31",
        currency_id=1,
        db=db,
    )

    monthly = result["monthly"]
    assert [item["month"] for item in monthly] == ["2024-01", "2024-02", "2024-03"]

    assert monthly[0]["assets_by_category"]["bienes"] == 1200.0
    assert monthly[0]["assets_by_category"]["inversiones"] == 500.0
    assert monthly[1]["assets_by_category"]["inversiones"] == 700.0
    assert monthly[2]["assets_by_category"]["inversiones"] == 600.0

    assert result["totals_by_category"]["bienes"] == 1200.0
    assert result["totals_by_category"]["inversiones"] == 600.0


def test_debt_balance_history_uses_principal_only():
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

    payment_jan = DebtPayment(
        debt_id=debt.id,
        payment_date=date(2024, 1, 15),
        amount=100.0,
    )
    adjustment_feb = DebtPayment(
        debt_id=debt.id,
        payment_date=date(2024, 2, 20),
        amount=-50.0,
    )
    db.add_all([payment_jan, adjustment_feb])
    db.commit()

    history = reports.get_debt_balance_history(
        start_date="2024-01-01",
        end_date="2024-02-28",
        currency_id=1,
        db=db,
    )

    monthly = history["monthly"]
    assert len(monthly) == 2
    assert monthly[0]["total_debt"] == 1000.0
    assert monthly[1]["total_debt"] == 1000.0
    assert "credit_loan" in monthly[0]["debt_by_type"]
