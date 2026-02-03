from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, List, Tuple

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session

from finance_app.models import (
    Currency,
    Debt,
    DebtPayment,
    ExchangeRate,
    MortgagePaymentAllocation,
    WealthAsset,
)
from finance_app.services.mortgage_service import calculate_monthly_payment


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


def _monthly_rate(annual_rate: float) -> float:
    if not annual_rate:
        return 0.0
    return (1 + annual_rate) ** (1 / 12) - 1


def _annual_rate_decimal(debt: Debt) -> float:
    if debt.annual_interest_rate is not None:
        try:
            rate = float(debt.annual_interest_rate)
        except (TypeError, ValueError):
            rate = 0.0
        return rate / 100 if rate > 1 else rate
    if debt.interest_rate:
        return debt.interest_rate / 100
    return 0.0


def _property_value_at_date(asset: WealthAsset, target_date: date) -> float:
    if asset.value is None:
        raise ValueError(f"El inmueble '{asset.name}' no tiene valor definido.")
    if not asset.as_of_date:
        raise ValueError(f"El inmueble '{asset.name}' no tiene fecha de compra/valoración.")
    if target_date < asset.as_of_date:
        return 0.0

    annual_rate = asset.expected_appreciation_rate or 0.0
    months_elapsed = max(
        0,
        (target_date.year - asset.as_of_date.year) * 12
        + (target_date.month - asset.as_of_date.month),
    )
    if months_elapsed == 0 or annual_rate == 0:
        return asset.value

    monthly_rate = _monthly_rate(annual_rate / 100)
    return asset.value * ((1 + monthly_rate) ** months_elapsed)


def _build_payment_map(
    db: Session,
    debt: Debt,
) -> Dict[Tuple[int, int], float]:
    payments: Dict[Tuple[int, int], float] = {}
    for payment in db.query(DebtPayment).filter_by(debt_id=debt.id).all():
        if not payment.payment_date:
            continue
        key = (payment.payment_date.year, payment.payment_date.month)
        payments[key] = payments.get(key, 0.0) + abs(payment.amount or 0.0)

    allocations = db.query(MortgagePaymentAllocation).filter_by(loan_id=debt.id).all()
    for allocation in allocations:
        if not allocation.payment_date:
            continue
        key = (allocation.payment_date.year, allocation.payment_date.month)
        total = (
            float(allocation.interest_paid or 0)
            + float(allocation.principal_paid or 0)
            + float(allocation.extra_principal_paid or 0)
            + float(allocation.fees_paid or 0)
            + float(allocation.escrow_paid or 0)
        )
        payments[key] = payments.get(key, 0.0) + total

    return payments


def _infer_monthly_payment(debt: Debt) -> float:
    if debt.monthly_payment and debt.monthly_payment > 0:
        return debt.monthly_payment

    if not debt.original_amount or debt.original_amount <= 0:
        raise ValueError(f"La deuda '{debt.name}' no tiene monto original válido.")

    if not debt.loan_years or debt.loan_years <= 0:
        raise ValueError(
            f"La deuda '{debt.name}' requiere plazo en años para calcular la cuota fija."
        )

    annual_rate = _annual_rate_decimal(debt)
    return calculate_monthly_payment(debt.original_amount, annual_rate, debt.loan_years)


def _build_debt_balance_map(
    db: Session,
    debt: Debt,
    end_month: date,
) -> Dict[date, float]:
    if not debt.start_date:
        raise ValueError(f"La deuda '{debt.name}' no tiene fecha de inicio.")
    if not debt.original_amount or debt.original_amount <= 0:
        raise ValueError(f"La deuda '{debt.name}' no tiene monto original válido.")

    monthly_payment = _infer_monthly_payment(debt)
    annual_rate = _annual_rate_decimal(debt)
    monthly_rate = _monthly_rate(annual_rate)
    payments_by_month = _build_payment_map(db, debt)

    balance = debt.original_amount
    balance_map: Dict[date, float] = {}
    current_month = _month_start(debt.start_date)

    for month_start in _iter_months(current_month, end_month):
        month_end = _month_end(month_start)
        if month_end < debt.start_date:
            balance_map[month_end] = 0.0
            continue

        balance += balance * monthly_rate
        payment = payments_by_month.get((month_start.year, month_start.month))
        if payment is None:
            payment = monthly_payment
        payment = min(payment, balance)
        balance = max(0.0, balance - payment)
        balance_map[month_end] = balance

        if balance <= 0:
            balance = 0.0

    return balance_map


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

    for asset in assets:
        if asset.mortgage_debt_id:
            mortgage = debt_by_id.get(asset.mortgage_debt_id)
            if not mortgage:
                raise ValueError(
                    f"El inmueble '{asset.name}' referencia una hipoteca inexistente."
                )
            if asset.mortgage_debt_id in linked_debt_ids:
                raise ValueError(
                    f"La hipoteca '{mortgage.name}' está asociada a más de un inmueble."
                )
            linked_debt_ids.add(asset.mortgage_debt_id)
        properties.append(asset)

    orphan_mortgages = [debt for debt in debts if debt.id not in linked_debt_ids]
    if orphan_mortgages:
        orphan_names = ", ".join(debt.name for debt in orphan_mortgages)
        raise ValueError(
            "Existen hipotecas sin inmueble asociado: " + orphan_names
        )

    start_month = _month_start(start_date)
    end_month = _month_start(end_date) + relativedelta(months=projection_months)
    today = date.today()

    debt_balance_maps = {
        debt.id: _build_debt_balance_map(db, debt, end_month)
        for debt in debts
    }
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
            value = _property_value_at_date(asset, month_end)
            converted_value = _convert_to_currency(
                value,
                asset.currency_id,
                currency_id,
                exchange_rate,
            )

            debt_balance = 0.0
            if asset.mortgage_debt_id:
                debt_balance = debt_balance_maps.get(asset.mortgage_debt_id, {}).get(
                    month_end,
                    0.0,
                )
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
    for asset in properties:
        value = _property_value_at_date(asset, today)
        converted_value = _convert_to_currency(
            value,
            asset.currency_id,
            currency_id,
            exchange_rate,
        )
        debt_balance = 0.0
        if asset.mortgage_debt_id:
            debt_balance = debt_balance_maps.get(asset.mortgage_debt_id, {}).get(
                _month_end(today),
                0.0,
            )
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
