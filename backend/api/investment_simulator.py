"""Investment simulator API."""
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services.investment_simulator_service import simulate_investment

router = APIRouter()


class InvestmentRequest(BaseModel):
    initial_amount: float = Field(..., gt=0)
    years: int = Field(..., gt=0)
    payment_frequency: str
    payment_type: str
    payment_amount: Optional[float] = None
    payment_percentage: Optional[float] = None
    historical_payments: Optional[List[float]] = None
    annual_valuation_rate: Optional[float] = 0.0
    start_date: Optional[str] = None


class InvestmentScheduleRow(BaseModel):
    payment_number: int
    date: str
    investment_value: float
    payment_amount: float
    payment_rate: float


class InvestmentResponse(BaseModel):
    schedule: List[InvestmentScheduleRow]
    total_payments: float
    payment_count: int
    projected_value: float
    historical_average_amount: float
    historical_average_percentage: float
    projected_average_amount: float
    projected_average_percentage: float
    used_payment_amount: Optional[float]
    used_payment_percentage: float
    frequency_months: int


@router.post("/calculate", response_model=InvestmentResponse)
def calculate_investment(request: InvestmentRequest):
    start_date_obj = None
    if request.start_date:
        if isinstance(request.start_date, str):
            start_date_obj = datetime.fromisoformat(request.start_date).date()
        elif isinstance(request.start_date, date):
            start_date_obj = request.start_date

    result = simulate_investment(
        initial_amount=request.initial_amount,
        years=request.years,
        payment_frequency=request.payment_frequency,
        payment_type=request.payment_type,
        payment_amount=request.payment_amount,
        payment_percentage=request.payment_percentage,
        historical_payments=request.historical_payments,
        annual_valuation_rate=request.annual_valuation_rate or 0.0,
        start_date=start_date_obj,
    )

    return InvestmentResponse(**result)


@router.get("/example")
def get_example():
    return {
        "initial_amount": 50000000,
        "years": 5,
        "payment_frequency": "monthly",
        "payment_type": "percentage",
        "payment_percentage": 0.8,
        "annual_valuation_rate": 6.0,
        "historical_payments": [200000, 220000, 210000],
    }
