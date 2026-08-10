"""Regression: domain FX must use the same USD-pivot rates as exchange_rate_service."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finance_app.database import Base
from finance_app.domain.fx.service import convert_to_cop, convert_to_cop_result
from finance_app.models import Currency, ExchangeRate
from finance_app.services.exchange_rate_service import convert_currency


def _make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_convert_to_cop_matches_service_for_eur_via_usd_pivot():
    db = _make_session()
    db.add_all([
        Currency(id=1, code="COP", symbol="$", name="Peso", is_base=True, decimals=0),
        Currency(id=2, code="USD", symbol="US$", name="Dollar", is_base=False, decimals=2),
        Currency(id=3, code="EUR", symbol="€", name="Euro", is_base=False, decimals=2),
        ExchangeRate(from_currency="USD", to_currency="COP", rate=4000.0, date=date(2024, 1, 1)),
        ExchangeRate(from_currency="USD", to_currency="EUR", rate=0.92, date=date(2024, 1, 1)),
    ])
    db.commit()

    as_of = date(2024, 6, 1)
    domain = float(convert_to_cop(100, "EUR", as_of, db=db))
    service = convert_currency(100, "EUR", "COP", db, rate_date=as_of)

    # Must not silently treat EUR as COP (identity = 100).
    assert domain != 100.0
    assert domain == pytest.approx(service)
    # 100 EUR → USD = 100/0.92; → COP = that * 4000
    assert domain == pytest.approx(100 / 0.92 * 4000, rel=1e-6)

    meta = convert_to_cop_result(100, "EUR", as_of, db=db)
    assert meta.used_fallback is False
    assert meta.rate_source == "service"
