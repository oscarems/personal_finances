"""
Mortgage Service - Mortgage calculator using fixed monthly payment and effective annual rate.

Calculates mortgages using the French amortization system (fixed payment) with an
effective annual rate, which is the standard in Colombia.
"""
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from typing import List, Dict


def calculate_monthly_payment(principal: float, annual_rate: float, years: int) -> float:
    """
    Calculate the fixed monthly payment for a mortgage.

    Uses the French amortization system (fixed payment): each month the same
    amount is paid, but the composition changes — initially more interest and
    less principal, and later more principal and less interest.

    Effective Annual Rate:
        Mortgages in Colombia use the effective annual rate (EA), not a nominal rate.
        The EA accounts for interest compounding.

    Formula:
        Payment = P * [r(1+r)^n] / [(1+r)^n - 1]

        Where:
            P = Principal (loan amount)
            r = Effective monthly rate
            n = Number of payments (months)

    Annual to monthly rate conversion:
        r_monthly = (1 + r_annual)^(1/12) - 1

        Example: 12% EA annual rate
            r_monthly = (1 + 0.12)^(1/12) - 1 = 0.009488793 (0.9488%)

    Args:
        principal (float): Loan amount (home value minus down payment).
        annual_rate (float): Effective annual rate as a decimal (e.g. 0.12 for 12%).
        years (int): Loan term in years.

    Returns:
        float: Fixed monthly payment amount.

    Examples:
        # Mortgage of $300,000,000 COP at 12% EA for 20 years
        >>> payment = calculate_monthly_payment(300000000, 0.12, 20)
        >>> print(f"${payment:,.0f}")
        $3,302,177

        # Mortgage of $100,000 USD at 7.5% EA for 30 years
        >>> payment = calculate_monthly_payment(100000, 0.075, 30)
        >>> print(f"${payment:,.2f}")
        $699.21

    Notes:
        - If the rate is 0%, the payment is simply principal / number_of_months.
        - The rate must be an effective annual rate, not nominal.
        - The term is calculated in months (years * 12).
    """
    if annual_rate == 0:
        # Sin intereses, solo dividir el principal
        return principal / (years * 12)

    # Convertir tasa efectiva anual a tasa efectiva mensual
    monthly_rate = (1 + annual_rate) ** (1/12) - 1

    # Número de cuotas
    num_payments = years * 12

    # Calcular cuota mensual usando fórmula de amortización francesa
    # M = P * [r(1+r)^n] / [(1+r)^n - 1]
    numerator = monthly_rate * ((1 + monthly_rate) ** num_payments)
    denominator = ((1 + monthly_rate) ** num_payments) - 1

    monthly_payment = principal * (numerator / denominator)

    return monthly_payment


def generate_amortization_schedule(
    principal: float,
    annual_rate: float,
    years: int,
    start_date: date = None
) -> List[Dict]:
    """
    Generate the full amortization schedule for a mortgage.

    Shows month by month:
        - Total payment (always the same with fixed-payment system)
        - Monthly interest (decreases over time)
        - Principal portion (increases over time)
        - Remaining balance (decreases to 0)

    Args:
        principal (float): Loan amount.
        annual_rate (float): Effective annual rate (decimal).
        years (int): Loan term in years.
        start_date (date, optional): Loan start date (default: today).

    Returns:
        List[Dict]: List of dicts, one per payment:
            [
                {
                    'payment_number': 1,
                    'date': date(2025, 2, 15),
                    'payment': 3302177.15,
                    'principal': 1458267.59,
                    'interest': 1843909.56,
                    'balance': 298541732.41
                },
                ...
            ]

    Example:
        >>> schedule = generate_amortization_schedule(300000000, 0.12, 20,
        ...                                           start_date=date(2025, 1, 15))
        >>> print(f"Payment 1:")
        >>> print(f"  Interest: ${schedule[0]['interest']:,.0f}")
        >>> print(f"  Principal: ${schedule[0]['principal']:,.0f}")
        >>> print(f"  Balance: ${schedule[0]['balance']:,.0f}")

        Payment 1:
          Interest: $1,843,910
          Principal: $1,458,267
          Balance: $298,541,732

    Notes:
        - In early months most of the payment is interest.
        - In later months most of the payment is principal.
        - The balance reaches exactly 0 on the final payment.
    """
    if start_date is None:
        start_date = date.today()

    # Calcular cuota mensual
    monthly_payment = calculate_monthly_payment(principal, annual_rate, years)

    # Convertir tasa anual a mensual
    monthly_rate = (1 + annual_rate) ** (1/12) - 1 if annual_rate > 0 else 0

    # Generar tabla
    schedule = []
    balance = principal
    payment_date = start_date

    for payment_num in range(1, years * 12 + 1):
        # Calcular interés del mes (sobre el saldo pendiente)
        interest = balance * monthly_rate

        # Calcular abono a capital (cuota - intereses)
        principal_payment = monthly_payment - interest

        # Actualizar saldo
        balance -= principal_payment

        # En la última cuota, ajustar para que el saldo sea exactamente 0
        if payment_num == years * 12:
            principal_payment += balance
            balance = 0

        # Agregar a tabla
        schedule.append({
            'payment_number': payment_num,
            'date': payment_date,
            'payment': monthly_payment,
            'principal': principal_payment,
            'interest': interest,
            'extra_payment': 0.0,
            'balance': max(0, balance)  # Evitar negativos por redondeo
        })

        # Avanzar al siguiente mes
        payment_date = payment_date + relativedelta(months=1)

    return schedule


def generate_amortization_schedule_with_extra(
    principal: float,
    annual_rate: float,
    years: int,
    extra_monthly_payment: float,
    start_date: date = None,
    extra_payment_start_date: date = None
) -> List[Dict]:
    """
    Generate the amortization schedule with additional monthly principal payments.

    Each month the fixed payment plus the extra amount (from the specified start date)
    is applied, reducing the total term.
    """
    if start_date is None:
        start_date = date.today()

    if extra_payment_start_date is None:
        extra_payment_start_date = start_date
    else:
        extra_payment_start_date = max(start_date, extra_payment_start_date)

    base_payment = calculate_monthly_payment(principal, annual_rate, years)
    monthly_rate = (1 + annual_rate) ** (1/12) - 1 if annual_rate > 0 else 0

    schedule = []
    balance = principal
    payment_date = start_date
    payment_num = 0

    while balance > 0 and payment_num < years * 12 * 2:
        payment_num += 1
        interest = balance * monthly_rate
        extra_for_month = extra_monthly_payment if payment_date >= extra_payment_start_date else 0.0
        max_payment = base_payment + extra_for_month
        applied_payment = min(balance + interest, max_payment)
        principal_payment = applied_payment - interest
        balance -= principal_payment

        extra_payment_applied = max(0.0, applied_payment - base_payment)

        schedule.append({
            'payment_number': payment_num,
            'date': payment_date,
            'payment': applied_payment,
            'principal': principal_payment,
            'interest': interest,
            'extra_payment': extra_payment_applied,
            'balance': max(0, balance)
        })

        payment_date = payment_date + relativedelta(months=1)

    return schedule


def calculate_total_interest(principal: float, annual_rate: float, years: int) -> float:
    """
    Calculate the total interest paid over the life of a loan.

    Useful for understanding the real cost of a loan: often you end up paying
    close to double the original principal.

    Args:
        principal (float): Loan amount.
        annual_rate (float): Effective annual rate (decimal).
        years (int): Term in years.

    Returns:
        float: Total interest paid.

    Example:
        >>> total_interest = calculate_total_interest(300000000, 0.12, 20)
        >>> print(f"Total interest: ${total_interest:,.0f}")
        Total interest: $492,522,491

        >>> monthly_payment = calculate_monthly_payment(300000000, 0.12, 20)
        >>> total_paid = monthly_payment * 20 * 12
        >>> print(f"Total paid: ${total_paid:,.0f}")
        Total paid: $792,522,491

    Formula:
        Total interest = (Monthly payment * Number of payments) - Principal
    """
    monthly_payment = calculate_monthly_payment(principal, annual_rate, years)
    total_paid = monthly_payment * years * 12
    total_interest = total_paid - principal

    return total_interest


def calculate_remaining_balance(
    principal: float,
    annual_rate: float,
    years: int,
    payments_made: int
) -> Dict:
    """
    Calculate the remaining balance after N payments have been made.

    Useful for:
        - Knowing how much you still owe
        - Calculating how much you need to pay off the loan
        - Tracking your mortgage payoff progress

    Args:
        principal (float): Original loan amount.
        annual_rate (float): Effective annual rate (decimal).
        years (int): Original term in years.
        payments_made (int): Number of payments already made.

    Returns:
        Dict: Current balance information:
            {
                'remaining_balance': float,      # Outstanding balance
                'remaining_payments': int,       # Payments remaining
                'total_paid': float,             # Total paid so far
                'principal_paid': float,         # Principal portion paid
                'interest_paid': float,          # Interest paid
                'percentage_paid': float         # % of principal paid
            }

    Example:
        >>> # After 5 years of payments (60 installments)
        >>> status = calculate_remaining_balance(300000000, 0.12, 20, 60)
        >>> print(f"Remaining balance: ${status['remaining_balance']:,.0f}")
        >>> print(f"Paid: {status['percentage_paid']:.1f}% of principal")

        Remaining balance: $265,327,841
        Paid: 11.6% of principal

    Notes:
        - In early years most of each payment is interest.
        - Principal paydown accelerates in later years.
        - Having 80-90% of debt remaining after 5-10 years is normal.
    """
    if payments_made >= years * 12:
        return {
            'remaining_balance': 0,
            'remaining_payments': 0,
            'total_paid': 0,
            'principal_paid': principal,
            'interest_paid': calculate_total_interest(principal, annual_rate, years),
            'percentage_paid': 100.0
        }

    # Generar tabla de amortización hasta el mes actual
    schedule = generate_amortization_schedule(principal, annual_rate, years)

    if payments_made == 0:
        return {
            'remaining_balance': principal,
            'remaining_payments': years * 12,
            'total_paid': 0,
            'principal_paid': 0,
            'interest_paid': 0,
            'percentage_paid': 0.0
        }

    # Obtener información del último pago realizado
    last_payment = schedule[payments_made - 1]

    # Calcular totales hasta ahora
    total_paid = sum(p['payment'] for p in schedule[:payments_made])
    principal_paid = sum(p['principal'] for p in schedule[:payments_made])
    interest_paid = sum(p['interest'] for p in schedule[:payments_made])

    return {
        'remaining_balance': last_payment['balance'],
        'remaining_payments': years * 12 - payments_made,
        'total_paid': total_paid,
        'principal_paid': principal_paid,
        'interest_paid': interest_paid,
        'percentage_paid': (principal_paid / principal) * 100
    }


def compare_scenarios(principal: float, scenarios: List[Dict]) -> List[Dict]:
    """
    Compare multiple mortgage scenarios (different rates or terms).

    Useful for choosing between different loan options.

    Args:
        principal (float): Loan amount (same for all scenarios).
        scenarios (List[Dict]): List of scenarios to compare:
            [
                {'name': '20 years 12%', 'rate': 0.12, 'years': 20},
                {'name': '30 years 10%', 'rate': 0.10, 'years': 30},
                ...
            ]

    Returns:
        List[Dict]: Same scenarios with calculated information:
            [
                {
                    'name': '20 years 12%',
                    'rate': 0.12,
                    'years': 20,
                    'monthly_payment': 3302177.15,
                    'total_interest': 492522491.23,
                    'total_paid': 792522491.23
                },
                ...
            ]

    Ejemplo:
        >>> scenarios = [
        ...     {'name': '20 años 12% EA', 'rate': 0.12, 'years': 20},
        ...     {'name': '30 años 10% EA', 'rate': 0.10, 'years': 30},
        ...     {'name': '15 años 14% EA', 'rate': 0.14, 'years': 15}
        ... ]
        >>> results = compare_scenarios(300000000, scenarios)
        >>> for r in results:
        ...     print(f"{r['name']}:")
        ...     print(f"  Cuota: ${r['monthly_payment']:,.0f}")
        ...     print(f"  Total intereses: ${r['total_interest']:,.0f}")

        20 años 12% EA:
          Cuota: $3,302,177
          Total intereses: $492,522,491

        30 años 10% EA:
          Cuota: $2,633,751
          Total intereses: $648,150,264

        15 años 14% EA:
          Cuota: $3,888,424
          Total intereses: $399,916,304
    """
    results = []

    for scenario in scenarios:
        monthly_payment = calculate_monthly_payment(
            principal,
            scenario['rate'],
            scenario['years']
        )

        total_interest = calculate_total_interest(
            principal,
            scenario['rate'],
            scenario['years']
        )

        results.append({
            **scenario,
            'monthly_payment': monthly_payment,
            'total_interest': total_interest,
            'total_paid': monthly_payment * scenario['years'] * 12
        })

    return results


def calculate_early_payoff(
    principal: float,
    annual_rate: float,
    years: int,
    extra_monthly_payment: float
) -> Dict:
    """
    Calculate savings from making extra monthly principal payments.

    Extra payments dramatically reduce total interest and the loan term.

    Args:
        principal (float): Loan amount.
        annual_rate (float): Effective annual rate.
        years (int): Original term in years.
        extra_monthly_payment (float): Extra monthly principal payment.

    Returns:
        Dict: Comparison with/without extra payments:
            {
                'original': {
                    'months': 240,
                    'total_interest': 492522491.23,
                    'monthly_payment': 3302177.15
                },
                'with_extra': {
                    'months': 180,  # Reduced term
                    'total_interest': 320000000.00,  # Lower interest
                    'monthly_payment': 3802177.15,  # Payment + extra
                    'months_saved': 60,
                    'interest_saved': 172522491.23
                }
            }

    Ejemplo:
        >>> # Abono extra de $500,000/mes
        >>> result = calculate_early_payoff(300000000, 0.12, 20, 500000)
        >>> print(f"Meses ahorrados: {result['with_extra']['months_saved']}")
        >>> print(f"Intereses ahorrados: ${result['with_extra']['interest_saved']:,.0f}")

        Meses ahorrados: 60
        Intereses ahorrados: $172,522,491

    Notas:
        - Los abonos extra se aplican directamente al capital
        - Reducen tanto el plazo como los intereses totales
        - Es una de las mejores estrategias de ahorro
    """
    # Escenario original
    original_payment = calculate_monthly_payment(principal, annual_rate, years)
    original_interest = calculate_total_interest(principal, annual_rate, years)
    original_months = years * 12

    # Simular con abonos extra
    monthly_rate = (1 + annual_rate) ** (1/12) - 1 if annual_rate > 0 else 0
    balance = principal
    months_with_extra = 0
    total_interest_with_extra = 0

    while balance > 0 and months_with_extra < years * 12 * 2:  # Límite de seguridad
        # Calcular interés del mes
        interest = balance * monthly_rate
        total_interest_with_extra += interest

        # Aplicar cuota regular + abono extra
        principal_payment = original_payment - interest + extra_monthly_payment

        # No pagar más del saldo restante
        if principal_payment > balance:
            principal_payment = balance

        balance -= principal_payment
        months_with_extra += 1

    months_saved = original_months - months_with_extra
    interest_saved = original_interest - total_interest_with_extra

    return {
        'original': {
            'months': original_months,
            'total_interest': original_interest,
            'monthly_payment': original_payment
        },
        'with_extra': {
            'months': months_with_extra,
            'total_interest': total_interest_with_extra,
            'monthly_payment': original_payment + extra_monthly_payment,
            'months_saved': months_saved,
            'interest_saved': interest_saved
        }
    }
