from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, List, Tuple

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from finance_app.models import (
    Currency,
    Debt,
    ExchangeRate,
    WealthAsset,
)
from finance_app.services.debt_amortization_service import (
    ensure_debt_amortization_records,
    fetch_amortization_for_month,
    fetch_amortization_range,
)


def _get_exchange_rate(db: Session) -> float:
    rate = db.query(ExchangeRate).order_by(ExchangeRate.date.desc()).first()
    return rate.rate if rate else 4000.0


def _convert_to_currency(
    amount: float,
    from_currency_id: int,
    to_currency_id: int,
    exchange_rate: float,
) -> float:
    if from_currency_id == to_currency_id:
        return amount
    if from_currency_id == 2 and to_currency_id == 1:
        return amount * exchange_rate
    if from_currency_id == 1 and to_currency_id == 2:
        return amount / exchange_rate
    return amount


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _month_end(day: date) -> date:
    return day.replace(day=1) + relativedelta(months=1) - relativedelta(days=1)


def _iter_months(start_month: date, end_month: date) -> Iterable[date]:
    current = start_month
    while current <= end_month:
        yield current
        current = current + relativedelta(months=1)


def _property_value_at_date(asset: WealthAsset, target_date: date) -> float:
    if asset.value is None:
        raise ValueError(f"El inmueble '{asset.name}' no tiene valor definido.")
    if not asset.as_of_date:
        raise ValueError(f"El inmueble '{asset.name}' no tiene fecha de compra/valoración.")
    if target_date < asset.as_of_date:
        return 0.0

    annual_rate = asset.expected_appreciation_rate or 0.0
    if target_date <= asset.as_of_date:
        return asset.value

    # Annual step appreciation: value increases once per year based on
    # the number of full years elapsed since acquisition.
    years_elapsed = max(0, target_date.year - asset.as_of_date.year)
    if years_elapsed == 0 or annual_rate == 0:
        return asset.value

    return asset.value * ((1 + (annual_rate / 100)) ** years_elapsed)


def build_real_estate_wealth_timeline(
    db: Session,
    start_date: date,
    end_date: date,
    projection_months: int,
    currency_id: int,
) -> dict:
    exchange_rate = _get_exchange_rate(db)
    currency = db.query(Currency).get(currency_id)
    assets = db.query(WealthAsset).filter(WealthAsset.asset_class == "inmueble").all()
    debts = db.query(Debt).filter(Debt.debt_type == "mortgage").all()
    debt_by_id = {debt.id: debt for debt in debts}

    linked_debt_ids: set[int] = set()
    properties: List[WealthAsset] = []
    # Map debt_id -> original_amount for fallback when no amortization record exists
    debt_original_amount: Dict[int, float] = {}

    for asset in assets:
        if asset.mortgage_debt_id:
            mortgage = debt_by_id.get(asset.mortgage_debt_id)
            if mortgage:
                if asset.mortgage_debt_id in linked_debt_ids:
                    raise ValueError(
                        f"La hipoteca '{mortgage.name}' está asociada a más de un inmueble."
                    )
                linked_debt_ids.add(asset.mortgage_debt_id)
                debt_original_amount[mortgage.id] = float(
                    mortgage.original_amount or mortgage.current_balance or 0.0
                )
        properties.append(asset)

    for mortgage in debts:
        if mortgage.id not in debt_original_amount:
            debt_original_amount[mortgage.id] = float(
                mortgage.original_amount or mortgage.current_balance or 0.0
            )

    orphan_mortgages = [debt for debt in debts if debt.id not in linked_debt_ids]

    start_month = _month_start(start_date)
    end_month = _month_start(end_date) + relativedelta(months=projection_months)
    today = date.today()

    ensure_debt_amortization_records(db, start_month, end_month)
    debt_ids = [debt.id for debt in debts]
    amortization_records = fetch_amortization_range(db, start_month, end_month, debt_ids)
    debt_currency_map = {debt.id: debt.currency_code for debt in debts if debt.currency_code}
    currency_map = {currency.code: currency.id for currency in db.query(Currency).all()}

    monthly: List[dict] = []
    for month_start in _iter_months(start_month, end_month):
        month_end = _month_end(month_start)
        month_type = "projected" if month_end > today else "real"

        property_value_total = 0.0
        debt_total = 0.0
        property_details = []

        for asset in properties:
            try:
                value = _property_value_at_date(asset, month_end)
            except ValueError:
                continue
            converted_value = _convert_to_currency(
                value,
                asset.currency_id,
                currency_id,
                exchange_rate,
            )

            debt_balance = 0.0
            if asset.mortgage_debt_id:
                amortization = amortization_records.get((asset.mortgage_debt_id, month_start))
                if amortization:
                    debt_balance = float(amortization.principal_remaining)
                else:
                    # Fallback: use original amount if month is after debt start
                    mortgage = debt_by_id.get(asset.mortgage_debt_id)
                    if mortgage and mortgage.start_date and month_start >= _month_start(mortgage.start_date):
                        debt_balance = debt_original_amount.get(asset.mortgage_debt_id, 0.0)
                debt_currency_id = currency_map.get(
                    debt_currency_map.get(asset.mortgage_debt_id, ""),
                    currency_id,
                )
                debt_balance = _convert_to_currency(
                    debt_balance,
                    debt_currency_id,
                    currency_id,
                    exchange_rate,
                )

            property_value_total += converted_value
            debt_total += debt_balance
            property_details.append({
                "id": asset.id,
                "name": asset.name,
                "property_value": round(converted_value, 2),
                "real_estate_debt": round(debt_balance, 2),
                "net_worth": round(converted_value - debt_balance, 2),
            })

        for mortgage in orphan_mortgages:
            amortization = amortization_records.get((mortgage.id, month_start))
            if amortization:
                debt_balance = float(amortization.principal_remaining)
            else:
                if mortgage.start_date and month_start >= _month_start(mortgage.start_date):
                    debt_balance = debt_original_amount.get(mortgage.id, 0.0)
                else:
                    debt_balance = 0.0
            debt_currency_id = currency_map.get(
                debt_currency_map.get(mortgage.id, ""),
                currency_id,
            )
            debt_balance = _convert_to_currency(
                debt_balance,
                debt_currency_id,
                currency_id,
                exchange_rate,
            )
            debt_total += debt_balance
            property_details.append({
                "id": f"mortgage-{mortgage.id}",
                "name": f"Hipoteca sin inmueble: {mortgage.name}",
                "property_value": 0.0,
                "real_estate_debt": round(debt_balance, 2),
                "net_worth": round(-debt_balance, 2),
            })

        monthly.append({
            "date": month_start.isoformat(),
            "property_value": round(property_value_total, 2),
            "real_estate_debt": round(debt_total, 2),
            "net_worth": round(property_value_total - debt_total, 2),
            "type": month_type,
            "properties": property_details,
        })

    current_property_value = 0.0
    current_debt_total = 0.0
    current_properties = []
    current_month = _month_start(today)
    current_amortization = fetch_amortization_for_month(db, current_month, debt_ids)
    for asset in properties:
        try:
            value = _property_value_at_date(asset, today)
        except ValueError:
            continue
        converted_value = _convert_to_currency(
            value,
            asset.currency_id,
            currency_id,
            exchange_rate,
        )
        debt_balance = 0.0
        if asset.mortgage_debt_id:
            amortization = current_amortization.get(asset.mortgage_debt_id)
            debt_balance = float(amortization.principal_remaining) if amortization else 0.0
            debt_currency_id = currency_map.get(
                debt_currency_map.get(asset.mortgage_debt_id, ""),
                currency_id,
            )
            debt_balance = _convert_to_currency(
                debt_balance,
                debt_currency_id,
                currency_id,
                exchange_rate,
            )

        current_property_value += converted_value
        current_debt_total += debt_balance
        current_properties.append({
            "id": asset.id,
            "name": asset.name,
            "property_value": round(converted_value, 2),
            "real_estate_debt": round(debt_balance, 2),
            "net_worth": round(converted_value - debt_balance, 2),
        })

    for mortgage in orphan_mortgages:
        amortization = current_amortization.get(mortgage.id)
        debt_balance = float(amortization.principal_remaining) if amortization else 0.0
        debt_currency_id = currency_map.get(
            debt_currency_map.get(mortgage.id, ""),
            currency_id,
        )
        debt_balance = _convert_to_currency(
            debt_balance,
            debt_currency_id,
            currency_id,
            exchange_rate,
        )
        current_debt_total += debt_balance
        current_properties.append({
            "id": f"mortgage-{mortgage.id}",
            "name": f"Hipoteca sin inmueble: {mortgage.name}",
            "property_value": 0.0,
            "real_estate_debt": round(debt_balance, 2),
            "net_worth": round(-debt_balance, 2),
        })

    real_months = [entry for entry in monthly if entry["type"] == "real"]
    if len(real_months) > 1:
        change = real_months[-1]["net_worth"] - real_months[0]["net_worth"]
        change_percentage = (
            (change / real_months[0]["net_worth"]) * 100
            if real_months[0]["net_worth"]
            else 0.0
        )
    else:
        change = 0.0
        change_percentage = 0.0

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "projection_end": end_month.isoformat(),
        "current": {
            "date": today.isoformat(),
            "property_value": round(current_property_value, 2),
            "real_estate_debt": round(current_debt_total, 2),
            "net_worth": round(current_property_value - current_debt_total, 2),
            "type": "real",
            "properties": current_properties,
        },
        "monthly": monthly,
        "change": round(change, 2),
        "change_percentage": round(change_percentage, 2),
        "currency": currency.to_dict() if currency else None,
    }
