from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import Account, Currency, Debt, Transaction, MortgagePaymentAllocation, ExchangeRate
from backend.services.transaction_service import create_transaction


def _make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_currency(db, code="COP", decimals=2):
    currency = Currency(id=1, code=code, symbol="$", name="Peso", is_base=True, decimals=decimals)
    db.add(currency)
    db.commit()
    return currency


def _seed_account(db, currency_id):
    account = Account(name="Cuenta", type="checking", currency_id=currency_id, balance=0.0, is_budget=True)
    db.add(account)
    db.commit()
    return account


def _seed_mortgage(db):
    loan = Debt(
        account_id=1,
        name="Hipoteca",
        debt_type="mortgage",
        currency_code="COP",
        original_amount=1000.0,
        current_balance=1000.0,
        annual_interest_rate=Decimal("12.0"),
        monthly_payment=150.0,
        start_date=date(2024, 1, 1),
        is_active=True,
        principal_balance=Decimal("1000.0"),
        interest_balance=Decimal("0.0"),
        last_accrual_date=date(2024, 1, 1),
    )
    db.add(loan)
    db.commit()
    return loan


def test_auto_mortgage_allocation_applies_interest_and_principal():
    db = _make_session()
    currency = _seed_currency(db)
    _seed_account(db, currency.id)
    loan = _seed_mortgage(db)

    transaction = create_transaction(db, {
        "account_id": 1,
        "date": date(2024, 2, 1),
        "payee_name": "Banco",
        "amount": -200.0,
        "currency_id": currency.id,
        "cleared": True,
        "mortgage_allocation": {
            "loan_id": loan.id,
            "payment_date": date(2024, 2, 1),
            "mode": "auto"
        }
    })

    allocation = db.query(MortgagePaymentAllocation).filter_by(transaction_id=transaction.id).one()
    assert allocation.interest_paid == Decimal("10.19")
    assert allocation.principal_paid == Decimal("139.81")
    assert allocation.extra_principal_paid == Decimal("50.00")

    refreshed_loan = db.query(Debt).get(loan.id)
    assert refreshed_loan.principal_balance == Decimal("810.19")
    assert refreshed_loan.interest_balance == Decimal("0.00")


def test_manual_allocation_requires_totals_match_payment():
    db = _make_session()
    currency = _seed_currency(db)
    _seed_account(db, currency.id)
    loan = _seed_mortgage(db)

    with pytest.raises(ValueError, match="Allocation total must equal mortgage payment amount"):
        create_transaction(db, {
            "account_id": 1,
            "date": date(2024, 2, 1),
            "payee_name": "Banco",
            "amount": -100.0,
            "currency_id": currency.id,
            "cleared": True,
            "mortgage_allocation": {
                "loan_id": loan.id,
                "payment_date": date(2024, 2, 1),
                "mode": "manual",
                "interest_paid": Decimal("10.00"),
                "principal_paid": Decimal("80.00"),
            }
        })


def test_allocation_rejects_currency_mismatch():
    db = _make_session()
    cop = _seed_currency(db, "COP", decimals=2)
    usd = Currency(id=2, code="USD", symbol="$", name="Dollar", is_base=False, decimals=2)
    db.add(usd)
    db.commit()
    db.add(ExchangeRate(
        from_currency="USD",
        to_currency="COP",
        rate=4000.0,
        date=date(2024, 2, 1)
    ))
    db.commit()
    _seed_account(db, usd.id)
    loan = _seed_mortgage(db)

    with pytest.raises(ValueError, match="Transaction currency does not match mortgage currency"):
        create_transaction(db, {
            "account_id": 1,
            "date": date(2024, 2, 1),
            "payee_name": "Banco",
            "amount": -200.0,
            "currency_id": usd.id,
            "cleared": True,
            "mortgage_allocation": {
                "loan_id": loan.id,
                "payment_date": date(2024, 2, 1),
                "mode": "auto"
            }
        })
