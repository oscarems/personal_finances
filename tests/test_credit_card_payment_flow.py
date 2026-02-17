from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finance_app.api.debts import get_debts
from finance_app.database import Base
from finance_app.models import Account, Currency, Debt
from finance_app.services.transaction_service import create_transaction, create_transfer


def _make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_currencies(db):
    cop = Currency(id=1, code="COP", symbol="$", name="Peso", is_base=True, decimals=0)
    db.add(cop)
    db.commit()


def test_credit_card_debt_balance_matches_account_after_card_payment_transfer():
    db = _make_session()
    _seed_currencies(db)

    checking = Account(name="Cuenta", type="checking", currency_id=1, balance=1_000_000)
    credit_card = Account(name="Tarjeta", type="credit_card", currency_id=1, balance=0)
    db.add_all([checking, credit_card])
    db.commit()

    debt = Debt(
        account_id=credit_card.id,
        name="Tarjeta",
        debt_type="credit_card",
        currency_code="COP",
        original_amount=500_000,
        current_balance=0,
        start_date=date.today(),
        is_active=True,
    )
    db.add(debt)
    db.commit()

    create_transaction(
        db,
        {
            "account_id": credit_card.id,
            "date": date.today(),
            "amount": -300_000,
            "currency_id": 1,
            "memo": "Compra",
        },
    )
    db.commit()

    db.refresh(credit_card)
    db.refresh(debt)
    assert credit_card.balance == -300_000
    assert debt.current_balance == 300_000

    create_transfer(
        db,
        {
            "from_account_id": checking.id,
            "to_account_id": credit_card.id,
            "date": date.today(),
            "amount": 100_000,
            "from_currency_id": 1,
            "to_currency_id": 1,
            "memo": "Pago tarjeta",
            "cleared": True,
        },
    )

    db.refresh(credit_card)
    db.refresh(debt)
    assert credit_card.balance == -200_000
    assert debt.current_balance == 200_000

    debts = get_debts(is_active=None, debt_type=None, db=db)
    cc_debt = next(item for item in debts if item["id"] == debt.id)
    assert cc_debt["current_balance"] == 200_000
