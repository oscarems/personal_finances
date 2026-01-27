"""
Investment Simulator Service.
"""
from datetime import date
from typing import Dict, List, Optional

from dateutil.relativedelta import relativedelta


FREQUENCY_MONTHS = {
    "monthly": 1,
    "bimonthly": 2,
    "quarterly": 3,
    "semiannual": 6,
    "annual": 12,
}


def _average(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def simulate_investment(
    initial_amount: float,
    years: int,
    payment_frequency: str,
    payment_type: str,
    payment_amount: Optional[float],
    payment_percentage: Optional[float],
    historical_payments: Optional[List[float]],
    annual_valuation_rate: float,
    start_date: Optional[date] = None,
) -> Dict:
    if initial_amount <= 0:
        raise ValueError("El monto inicial debe ser mayor a 0")

    if years <= 0:
        raise ValueError("El plazo debe ser mayor a 0")

    if payment_frequency not in FREQUENCY_MONTHS:
        raise ValueError("Frecuencia de pago inválida")

    if payment_type not in {"fixed", "percentage", "historical"}:
        raise ValueError("Tipo de pago inválido")

    if start_date is None:
        start_date = date.today()

    historical_payments = historical_payments or []
    historical_payments = historical_payments[:12]

    average_historical_amount = _average(historical_payments)
    average_historical_percentage = (
        (average_historical_amount / initial_amount) * 100
        if initial_amount
        else 0.0
    )

    if payment_type == "fixed":
        if payment_amount is None or payment_amount < 0:
            raise ValueError("Monto fijo inválido")
        used_payment_amount = payment_amount
        used_payment_percentage = (
            (payment_amount / initial_amount) * 100 if initial_amount else 0.0
        )
    elif payment_type == "percentage":
        if payment_percentage is None or payment_percentage < 0:
            raise ValueError("Porcentaje inválido")
        used_payment_amount = None
        used_payment_percentage = payment_percentage
    else:
        used_payment_amount = average_historical_amount
        used_payment_percentage = average_historical_percentage

    frequency_months = FREQUENCY_MONTHS[payment_frequency]
    total_months = years * 12
    monthly_rate = (
        (1 + (annual_valuation_rate / 100)) ** (1 / 12) - 1
        if annual_valuation_rate
        else 0.0
    )

    schedule = []
    investment_value = initial_amount
    payment_count = 0
    total_payments = 0.0
    payment_date = start_date

    for month in range(1, total_months + 1):
        investment_value *= (1 + monthly_rate)

        if month % frequency_months == 0:
            payment_count += 1
            if payment_type == "percentage":
                payment = investment_value * (used_payment_percentage / 100)
            else:
                payment = used_payment_amount

            payment_rate = (
                (payment / investment_value) * 100 if investment_value else 0.0
            )

            schedule.append({
                "payment_number": payment_count,
                "date": payment_date.isoformat(),
                "investment_value": investment_value,
                "payment_amount": payment,
                "payment_rate": payment_rate,
            })

            total_payments += payment

        payment_date = payment_date + relativedelta(months=1)

    projected_average_payment = (
        total_payments / payment_count if payment_count else 0.0
    )
    projected_average_rate = (
        (projected_average_payment / initial_amount) * 100
        if initial_amount
        else 0.0
    )

    return {
        "schedule": schedule,
        "total_payments": total_payments,
        "payment_count": payment_count,
        "projected_value": investment_value,
        "historical_average_amount": average_historical_amount,
        "historical_average_percentage": average_historical_percentage,
        "projected_average_amount": projected_average_payment,
        "projected_average_percentage": projected_average_rate,
        "used_payment_amount": used_payment_amount,
        "used_payment_percentage": used_payment_percentage,
        "frequency_months": frequency_months,
    }
