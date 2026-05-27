"""
Mortgage Simulator API - Fixed payment with effective annual rate.

Uses the EFFECTIVE ANNUAL RATE (EA), which is the standard in Colombia.
The effective annual rate accounts for interest compounding, unlike the nominal rate.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import date

from sqlalchemy.orm import Session

from finance_app.database import get_db
from finance_app.models.account import Account
from finance_app.services.mortgage.service import (
    calculate_monthly_payment,
    generate_amortization_schedule,
    generate_amortization_schedule_with_extra,
    calculate_total_interest,
    compare_scenarios
)

router = APIRouter()


class MortgageRequest(BaseModel):
    """Schema for a mortgage calculation request."""
    principal: float  # Loan amount
    annual_rate: float  # Effective annual rate as a percentage (e.g. 12.5 for 12.5% EA)
    years: int  # Term in years (converted to months internally)
    start_date: Optional[str] = None  # Fecha de inicio (opcional, default: hoy)
    extra_payment: Optional[float] = None  # Pago extra mensual al capital
    extra_payment_start_date: Optional[str] = None  # Fecha desde la que aplica el pago extra


class AmortizationRow(BaseModel):
    """Amortization table row."""
    payment_number: int
    date: str
    payment: float
    principal: float
    interest: float
    extra_payment: float = 0.0
    balance: float


class MortgageResponse(BaseModel):
    """Response with complete mortgage calculation."""
    monthly_payment: float
    total_interest: float
    total_paid: float
    months: int
    years: float
    payoff_date: str
    months_saved: int = 0
    interest_saved: float = 0.0
    schedule: List[AmortizationRow]
    # Información adicional si hay abonos extra
    with_extra: Optional[dict] = None


class ScenarioRequest(BaseModel):
    """Schema for comparing multiple mortgage scenarios."""
    principal: float
    scenarios: List[dict]  # [{"name": "20 años 12%", "rate": 0.12, "years": 20}]


@router.post("/calculate", response_model=MortgageResponse)
def calculate_mortgage(request: MortgageRequest):
    """
    Calculate a mortgage with fixed payment and effective annual rate.

    POST /api/mortgage/calculate
    {
        "principal": 300000000,
        "annual_rate": 12.5,  // Effective annual rate in % (12.5% EA)
        "years": 20,
        "start_date": "2025-01-15",  // Optional
        "extra_payment": 500000,  // Optional: extra monthly principal payment
        "extra_payment_start_date": "2025-06-01"  // Optional: when extra payment starts
    }
    """
    # Convertir tasa de porcentaje a decimal
    rate_decimal = request.annual_rate / 100

    # Convertir start_date de string a date si es necesario
    start_date_obj = None
    if request.start_date:
        if isinstance(request.start_date, str):
            from datetime import datetime
            start_date_obj = datetime.fromisoformat(request.start_date).date()
        else:
            start_date_obj = request.start_date

    extra_payment_start_date_obj = None
    if request.extra_payment_start_date:
        if isinstance(request.extra_payment_start_date, str):
            from datetime import datetime
            extra_payment_start_date_obj = datetime.fromisoformat(
                request.extra_payment_start_date
            ).date()
        else:
            extra_payment_start_date_obj = request.extra_payment_start_date

    base_payment = calculate_monthly_payment(
        request.principal,
        rate_decimal,
        request.years
    )

    if request.extra_payment is not None and request.extra_payment > 0:
        schedule = generate_amortization_schedule_with_extra(
            request.principal,
            rate_decimal,
            request.years,
            request.extra_payment,
            start_date_obj,
            extra_payment_start_date_obj
        )
        monthly_payment = schedule[0]["payment"] if schedule else base_payment
        total_interest = sum(row["interest"] for row in schedule)
        total_paid = sum(row["payment"] for row in schedule)
        months = len(schedule)
        years = months / 12
        payoff_date = schedule[-1]["date"].isoformat() if schedule else date.today().isoformat()
        base_schedule = generate_amortization_schedule(
            request.principal,
            rate_decimal,
            request.years,
            start_date_obj
        )
        base_total_interest = sum(row["interest"] for row in base_schedule)
        months_saved = max(0, len(base_schedule) - months)
        interest_saved = max(0.0, base_total_interest - total_interest)
        with_extra = {
            "extra_payment_start_date": (
                extra_payment_start_date_obj.isoformat()
                if extra_payment_start_date_obj
                else None
            ),
            "months_saved": months_saved,
            "interest_saved": interest_saved
        }
    else:
        schedule = generate_amortization_schedule(
            request.principal,
            rate_decimal,
            request.years,
            start_date_obj
        )
        monthly_payment = base_payment
        total_interest = calculate_total_interest(
            request.principal,
            rate_decimal,
            request.years
        )
        total_paid = monthly_payment * request.years * 12
        months = request.years * 12
        years = request.years
        payoff_date = schedule[-1]["date"].isoformat() if schedule else date.today().isoformat()
        months_saved = 0
        interest_saved = 0.0
        with_extra = None

    response = {
        "monthly_payment": monthly_payment,
        "total_interest": total_interest,
        "total_paid": total_paid,
        "months": months,
        "years": years,
        "payoff_date": payoff_date,
        "months_saved": months_saved,
        "interest_saved": interest_saved,
        "schedule": [
            {
                "payment_number": row["payment_number"],
                "date": row["date"].isoformat(),
                "payment": row["payment"],
                "principal": row["principal"],
                "interest": row["interest"],
                "extra_payment": row.get("extra_payment", 0.0),
                "balance": row["balance"]
            }
            for row in schedule
        ],
        "with_extra": with_extra
    }

    return MortgageResponse(**response)


@router.post("/compare")
def compare_mortgage_scenarios(request: ScenarioRequest):
    """
    Compare multiple mortgage scenarios.

    POST /api/mortgage/compare
    {
        "principal": 300000000,
        "scenarios": [
            {"name": "20 years 12% EA", "rate": 0.12, "years": 20},
            {"name": "30 years 10% EA", "rate": 0.10, "years": 30},
            {"name": "15 years 14% EA", "rate": 0.14, "years": 15}
        ]
    }

    Returns each scenario with:
    - Monthly payment
    - Total interest
    - Total paid
    """
    results = compare_scenarios(request.principal, request.scenarios)
    return {"scenarios": results}


@router.get("/example")
def get_example():
    """Get an example mortgage calculation."""
    return {
        "principal": 300000000,  # $300M COP
        "annual_rate": 12.5,  # 12.5% EA
        "years": 20,
        "start_date": "2025-01-15",
        "extra_payment": 0
    }


@router.get("/accounts")
def list_mortgage_accounts(db: Session = Depends(get_db)):
    """Return all accounts of type 'mortgage'."""
    accounts = db.query(Account).filter_by(type="mortgage", is_closed=False).all()
    result = []
    for acc in accounts:
        data = acc.to_dict()
        # Attach linked debt info if available
        debt = next((d for d in acc.debts if d.debt_type == "mortgage"), None)
        if debt:
            rate = None
            if debt.annual_interest_rate is not None:
                v = float(debt.annual_interest_rate)
                rate = v if v > 1 else v * 100
            elif debt.interest_rate is not None:
                rate = debt.interest_rate
            data.setdefault("interest_rate", rate)
            data.setdefault("monthly_payment", debt.monthly_payment)
            data["term_months"] = debt.term_months
            data["loan_start_date"] = debt.start_date.isoformat() if debt.start_date else None
            data["original_amount"] = debt.original_amount
        result.append(data)
    return result


@router.get("/{account_id}/schedule")
def get_mortgage_schedule(account_id: int, db: Session = Depends(get_db)):
    """Generate the amortization schedule for a mortgage account."""
    acc = db.query(Account).filter_by(id=account_id, type="mortgage").first()
    if not acc:
        raise HTTPException(status_code=404, detail="Hipoteca no encontrada")

    # Resolve interest rate: account field > linked debt fields
    rate = acc.interest_rate
    debt = next((d for d in acc.debts if d.debt_type == "mortgage"), None)
    if rate is None and debt:
        if debt.annual_interest_rate is not None:
            v = float(debt.annual_interest_rate)
            rate = v if v > 1 else v * 100
        elif debt.interest_rate is not None:
            rate = debt.interest_rate

    if rate is None:
        raise HTTPException(
            status_code=422,
            detail="La hipoteca no tiene tasa de interés registrada. "
                   "Actualiza la tasa en la sección de Cuentas para ver la tabla de amortización."
        )

    balance = abs(acc.balance or 0)
    if balance == 0 and debt:
        balance = debt.current_balance or 0

    # Resolve term in years
    years = acc.loan_years
    if years is None and debt:
        years = debt.loan_years or (debt.term_months // 12 if debt.term_months else None)
    if years is None:
        # Estimate from balance and monthly payment
        mp = acc.monthly_payment or (debt.monthly_payment if debt else None)
        if mp and mp > 0 and rate:
            mr = (1 + rate / 100) ** (1 / 12) - 1
            if mr > 0 and balance * mr / mp < 1:
                import math
                n = -math.log(1 - balance * mr / mp) / math.log(1 + mr)
                years = max(1, math.ceil(n / 12))
        if years is None:
            raise HTTPException(status_code=422, detail="No se pudo determinar el plazo de la hipoteca.")

    # Resolve start date
    start_date = acc.loan_start_date
    if start_date is None and debt and debt.start_date:
        start_date = debt.start_date

    schedule = generate_amortization_schedule(
        principal=balance,
        annual_rate=rate / 100,
        years=int(years),
        start_date=start_date,
    )

    return {
        "account_id": account_id,
        "annual_rate": rate,
        "years": years,
        "schedule": [
            {
                "payment_number": r["payment_number"],
                "date": r["date"].isoformat(),
                "payment": r["payment"],
                "principal": r["principal"],
                "interest": r["interest"],
                "balance": r["balance"],
            }
            for r in schedule
        ],
    }
