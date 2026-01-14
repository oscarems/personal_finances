"""
Mortgage Simulator API
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

router = APIRouter()


class MortgageRequest(BaseModel):
    principal: float  # Monto del préstamo
    annual_rate: float  # Tasa de interés anual (%)
    term_months: int  # Plazo en meses
    start_date: date  # Fecha de inicio
    extra_payment: Optional[float] = 0  # Pago extra mensual


class AmortizationRow(BaseModel):
    payment_number: int
    date: str
    payment: float
    principal: float
    interest: float
    extra_payment: float
    balance: float


class MortgageResponse(BaseModel):
    monthly_payment: float
    total_payments: float
    total_interest: float
    total_principal: float
    total_extra: float
    payoff_date: str
    months_saved: int
    interest_saved: float
    schedule: List[AmortizationRow]


def calculate_monthly_payment(principal: float, monthly_rate: float, term_months: int) -> float:
    """Calculate fixed monthly payment (French amortization)"""
    if monthly_rate == 0:
        return principal / term_months

    return principal * (monthly_rate * (1 + monthly_rate) ** term_months) / \
           ((1 + monthly_rate) ** term_months - 1)


def generate_amortization_schedule(
    principal: float,
    annual_rate: float,
    term_months: int,
    start_date: date,
    extra_payment: float = 0
) -> dict:
    """
    Generate complete amortization schedule
    Returns dict with summary stats and schedule
    """
    monthly_rate = annual_rate / 100 / 12
    monthly_payment = calculate_monthly_payment(principal, monthly_rate, term_months)

    # Generate schedule with extra payments
    balance = principal
    schedule = []
    current_date = start_date
    payment_num = 0

    total_interest = 0
    total_principal = 0
    total_extra = 0

    while balance > 0 and payment_num < term_months * 2:  # Safety limit
        payment_num += 1

        # Interest for this month
        interest = balance * monthly_rate

        # Principal payment (fixed payment - interest)
        principal_payment = monthly_payment - interest

        # Extra payment (applied to principal)
        extra = extra_payment if balance > monthly_payment else 0

        # Total principal reduction
        total_principal_reduction = principal_payment + extra

        # Ensure we don't overpay
        if total_principal_reduction > balance:
            total_principal_reduction = balance
            extra = balance - principal_payment
            if extra < 0:
                extra = 0

        # New balance
        new_balance = balance - total_principal_reduction

        # Record payment
        schedule.append({
            'payment_number': payment_num,
            'date': current_date.isoformat(),
            'payment': monthly_payment,
            'principal': principal_payment,
            'interest': interest,
            'extra_payment': extra,
            'balance': new_balance
        })

        # Update totals
        total_interest += interest
        total_principal += principal_payment
        total_extra += extra
        balance = new_balance

        # Move to next month
        current_date += relativedelta(months=1)

    # Calculate original schedule (no extra payments) for comparison
    original_schedule = generate_original_schedule(principal, annual_rate, term_months, start_date)

    months_saved = len(original_schedule) - len(schedule)
    interest_saved = sum(row['interest'] for row in original_schedule) - total_interest

    return {
        'monthly_payment': monthly_payment,
        'total_payments': monthly_payment * len(schedule) + total_extra,
        'total_interest': total_interest,
        'total_principal': total_principal,
        'total_extra': total_extra,
        'payoff_date': schedule[-1]['date'] if schedule else start_date.isoformat(),
        'months_saved': months_saved if extra_payment > 0 else 0,
        'interest_saved': interest_saved if extra_payment > 0 else 0,
        'schedule': schedule
    }


def generate_original_schedule(
    principal: float,
    annual_rate: float,
    term_months: int,
    start_date: date
) -> List[dict]:
    """Generate original schedule without extra payments"""
    monthly_rate = annual_rate / 100 / 12
    monthly_payment = calculate_monthly_payment(principal, monthly_rate, term_months)

    balance = principal
    schedule = []
    current_date = start_date

    for payment_num in range(1, term_months + 1):
        interest = balance * monthly_rate
        principal_payment = monthly_payment - interest
        balance -= principal_payment

        schedule.append({
            'payment_number': payment_num,
            'date': current_date.isoformat(),
            'payment': monthly_payment,
            'principal': principal_payment,
            'interest': interest,
            'extra_payment': 0,
            'balance': max(0, balance)
        })

        current_date += relativedelta(months=1)

    return schedule


@router.post("/calculate", response_model=MortgageResponse)
def calculate_mortgage(request: MortgageRequest):
    """Calculate mortgage amortization schedule"""
    result = generate_amortization_schedule(
        principal=request.principal,
        annual_rate=request.annual_rate,
        term_months=request.term_months,
        start_date=request.start_date,
        extra_payment=request.extra_payment or 0
    )

    return MortgageResponse(**result)


@router.get("/example")
def get_example():
    """Get example mortgage calculation"""
    return {
        "principal": 200000000,  # $200M COP
        "annual_rate": 12.5,  # 12.5% annual
        "term_months": 240,  # 20 years
        "start_date": "2024-01-01",
        "extra_payment": 0
    }
