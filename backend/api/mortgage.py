"""
Mortgage Simulator API - Con tasa efectiva anual y cuota fija

IMPORTANTE: Este simulador usa TASA EFECTIVA ANUAL (EA), que es el estándar en Colombia.
La tasa efectiva anual considera la capitalización de intereses, a diferencia de la
tasa nominal.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from datetime import date

from backend.services.mortgage_service import (
    calculate_monthly_payment,
    generate_amortization_schedule,
    calculate_total_interest,
    calculate_early_payoff,
    compare_scenarios
)

router = APIRouter()


class MortgageRequest(BaseModel):
    """Schema para solicitud de cálculo de hipoteca"""
    principal: float  # Monto del préstamo
    annual_rate: float  # Tasa efectiva anual como porcentaje (ej: 12.5 para 12.5% EA)
    years: int  # Plazo en años (se convertirá a meses internamente)
    start_date: Optional[str] = None  # Fecha de inicio (opcional, default: hoy)
    extra_payment: Optional[float] = None  # Pago extra mensual al capital


class AmortizationRow(BaseModel):
    """Fila de la tabla de amortización"""
    payment_number: int
    date: str
    payment: float
    principal: float
    interest: float
    balance: float


class MortgageResponse(BaseModel):
    """Respuesta con cálculo completo de hipoteca"""
    monthly_payment: float
    total_interest: float
    total_paid: float
    months: int
    years: float
    schedule: List[AmortizationRow]
    # Información adicional si hay abonos extra
    with_extra: Optional[dict] = None


class ScenarioRequest(BaseModel):
    """Schema para comparar múltiples escenarios"""
    principal: float
    scenarios: List[dict]  # [{"name": "20 años 12%", "rate": 0.12, "years": 20}]


@router.post("/calculate", response_model=MortgageResponse)
def calculate_mortgage(request: MortgageRequest):
    """
    Calcula hipoteca con cuota fija y tasa efectiva anual.

    POST /api/mortgage/calculate
    {
        "principal": 300000000,
        "annual_rate": 12.5,  // Tasa efectiva anual en % (12.5%)
        "years": 20,
        "start_date": "2025-01-15",  // Opcional
        "extra_payment": 500000  // Opcional: abono extra mensual
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

    # Calcular cuota mensual
    monthly_payment = calculate_monthly_payment(
        request.principal,
        rate_decimal,
        request.years
    )

    # Generar tabla de amortización
    schedule = generate_amortization_schedule(
        request.principal,
        rate_decimal,
        request.years,
        start_date_obj
    )

    # Calcular total de intereses
    total_interest = calculate_total_interest(
        request.principal,
        rate_decimal,
        request.years
    )

    # Preparar respuesta base
    response = {
        "monthly_payment": monthly_payment,
        "total_interest": total_interest,
        "total_paid": monthly_payment * request.years * 12,
        "months": request.years * 12,
        "years": request.years,
        "schedule": [
            {
                "payment_number": row["payment_number"],
                "date": row["date"].isoformat(),
                "payment": row["payment"],
                "principal": row["principal"],
                "interest": row["interest"],
                "balance": row["balance"]
            }
            for row in schedule
        ]
    }

    # Si hay abonos extra, calcular escenario con abonos
    if request.extra_payment is not None and request.extra_payment > 0:
        early_payoff = calculate_early_payoff(
            request.principal,
            rate_decimal,
            request.years,
            request.extra_payment
        )
        response["with_extra"] = early_payoff["with_extra"]

    return MortgageResponse(**response)


@router.post("/compare")
def compare_mortgage_scenarios(request: ScenarioRequest):
    """
    Compara múltiples escenarios de hipoteca.

    POST /api/mortgage/compare
    {
        "principal": 300000000,
        "scenarios": [
            {"name": "20 años 12% EA", "rate": 0.12, "years": 20},
            {"name": "30 años 10% EA", "rate": 0.10, "years": 30},
            {"name": "15 años 14% EA", "rate": 0.14, "years": 15}
        ]
    }

    Retorna cada escenario con:
    - Cuota mensual
    - Total de intereses
    - Total a pagar
    """
    results = compare_scenarios(request.principal, request.scenarios)
    return {"scenarios": results}


@router.get("/example")
def get_example():
    """Obtiene un ejemplo de cálculo de hipoteca"""
    return {
        "principal": 300000000,  # $300M COP
        "annual_rate": 12.5,  # 12.5% EA
        "years": 20,
        "start_date": "2025-01-15",
        "extra_payment": 0
    }
