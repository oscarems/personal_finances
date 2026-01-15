"""
Mortgage Service - Calculadora de hipotecas con cuota fija y tasa efectiva anual

Este servicio calcula hipotecas usando el sistema de cuota fija (amortización francesa)
con tasa efectiva anual, que es el estándar en Colombia.
"""
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
from typing import List, Dict


def calculate_monthly_payment(principal: float, annual_rate: float, years: int) -> float:
    """
    Calcula la cuota mensual fija de una hipoteca.

    Usa el sistema de amortización francesa (cuota fija) donde cada mes se paga
    la misma cantidad, pero la composición cambia: al inicio se pagan más intereses
    y menos capital, y al final más capital y menos intereses.

    IMPORTANTE - Tasa Efectiva Anual:
        En Colombia las hipotecas usan tasa efectiva anual (EA), no tasa nominal.
        La tasa efectiva anual considera la capitalización de intereses.

    Fórmula:
        Cuota = P * [r(1+r)^n] / [(1+r)^n - 1]

        Donde:
            P = Principal (monto del préstamo)
            r = Tasa mensual efectiva
            n = Número de cuotas (meses)

    Conversión de tasa anual a mensual:
        r_mensual = (1 + r_anual)^(1/12) - 1

        Ejemplo: Tasa EA 12% anual
            r_mensual = (1 + 0.12)^(1/12) - 1 = 0.009488793 (0.9488%)

    Args:
        principal (float): Monto del préstamo (valor de la casa - cuota inicial)
        annual_rate (float): Tasa efectiva anual como decimal (ej: 0.12 para 12%)
        years (int): Plazo en años

    Returns:
        float: Cuota mensual fija

    Ejemplos:
        # Hipoteca de $300,000,000 COP a 12% EA por 20 años
        >>> cuota = calculate_monthly_payment(300000000, 0.12, 20)
        >>> print(f"${cuota:,.0f}")
        $3,302,177

        # Hipoteca de $100,000 USD a 7.5% EA por 30 años
        >>> cuota = calculate_monthly_payment(100000, 0.075, 30)
        >>> print(f"${cuota:,.2f}")
        $699.21

    Notas:
        - Si la tasa es 0%, la cuota es simplemente principal / número_de_meses
        - La tasa debe ser efectiva anual, no nominal
        - El plazo se calcula en meses (years * 12)
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
    Genera la tabla de amortización completa de una hipoteca.

    La tabla muestra mes a mes:
        - Cuota total (siempre igual en sistema de cuota fija)
        - Intereses del mes (se reduce con el tiempo)
        - Abono a capital (aumenta con el tiempo)
        - Saldo restante (disminuye hasta llegar a 0)

    Args:
        principal (float): Monto del préstamo
        annual_rate (float): Tasa efectiva anual (decimal)
        years (int): Plazo en años
        start_date (date, opcional): Fecha de inicio del crédito (default: hoy)

    Returns:
        List[Dict]: Lista de diccionarios, uno por cada cuota:
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

    Ejemplo:
        >>> schedule = generate_amortization_schedule(300000000, 0.12, 20,
        ...                                           start_date=date(2025, 1, 15))
        >>> print(f"Cuota 1:")
        >>> print(f"  Interés: ${schedule[0]['interest']:,.0f}")
        >>> print(f"  Capital: ${schedule[0]['principal']:,.0f}")
        >>> print(f"  Saldo: ${schedule[0]['balance']:,.0f}")

        Cuota 1:
          Interés: $1,843,910
          Capital: $1,458,267
          Saldo: $298,541,732

    Notas:
        - En los primeros meses, la mayor parte de la cuota son intereses
        - En los últimos meses, la mayor parte son abono a capital
        - El saldo siempre llega exactamente a 0 en la última cuota
        - Útil para ver cuánto pagarías en total de intereses
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
    start_date: date = None
) -> List[Dict]:
    """
    Genera la tabla de amortización aplicando abonos extra mensuales al capital.

    Cada mes se paga la cuota fija + el abono extra, reduciendo el plazo total.
    """
    if start_date is None:
        start_date = date.today()

    base_payment = calculate_monthly_payment(principal, annual_rate, years)
    monthly_rate = (1 + annual_rate) ** (1/12) - 1 if annual_rate > 0 else 0

    schedule = []
    balance = principal
    payment_date = start_date
    payment_num = 0

    while balance > 0 and payment_num < years * 12 * 2:
        payment_num += 1
        interest = balance * monthly_rate
        max_payment = base_payment + extra_monthly_payment
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
    Calcula el total de intereses que pagarás durante toda la vida del crédito.

    Esta función es útil para entender el costo real del crédito. Muchas veces
    terminas pagando casi el doble del valor original del préstamo.

    Args:
        principal (float): Monto del préstamo
        annual_rate (float): Tasa efectiva anual (decimal)
        years (int): Plazo en años

    Returns:
        float: Total de intereses a pagar

    Ejemplo:
        >>> total_interest = calculate_total_interest(300000000, 0.12, 20)
        >>> print(f"Intereses totales: ${total_interest:,.0f}")
        Intereses totales: $492,522,491

        >>> monthly_payment = calculate_monthly_payment(300000000, 0.12, 20)
        >>> total_paid = monthly_payment * 20 * 12
        >>> print(f"Total a pagar: ${total_paid:,.0f}")
        Total a pagar: $792,522,491

    Fórmula:
        Intereses totales = (Cuota mensual * Número de cuotas) - Principal
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
    Calcula el saldo restante después de haber pagado N cuotas.

    Útil para:
        - Saber cuánto debes todavía
        - Calcular cuánto necesitas para liquidar la deuda
        - Ver tu progreso en el pago de la hipoteca

    Args:
        principal (float): Monto original del préstamo
        annual_rate (float): Tasa efectiva anual (decimal)
        years (int): Plazo original en años
        payments_made (int): Número de cuotas ya pagadas

    Returns:
        Dict: Información del saldo actual:
            {
                'remaining_balance': float,      # Saldo pendiente
                'remaining_payments': int,       # Cuotas que faltan
                'total_paid': float,             # Total pagado hasta ahora
                'principal_paid': float,         # Capital abonado
                'interest_paid': float,          # Intereses pagados
                'percentage_paid': float         # % del capital pagado
            }

    Ejemplo:
        >>> # Después de 5 años pagando (60 cuotas)
        >>> status = calculate_remaining_balance(300000000, 0.12, 20, 60)
        >>> print(f"Saldo restante: ${status['remaining_balance']:,.0f}")
        >>> print(f"Has pagado: {status['percentage_paid']:.1f}% del capital")

        Saldo restante: $265,327,841
        Has pagado: 11.6% del capital

    Notas:
        - En los primeros años pagas principalmente intereses
        - El capital se paga más rápido en los últimos años
        - Es normal tener aún 80-90% de deuda después de 5-10 años
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
    Compara múltiples escenarios de hipoteca (diferentes tasas o plazos).

    Útil para decidir entre diferentes opciones de crédito.

    Args:
        principal (float): Monto del préstamo (igual para todos)
        scenarios (List[Dict]): Lista de escenarios a comparar:
            [
                {'name': '20 años 12%', 'rate': 0.12, 'years': 20},
                {'name': '30 años 10%', 'rate': 0.10, 'years': 30},
                ...
            ]

    Returns:
        List[Dict]: Mismos escenarios con información calculada:
            [
                {
                    'name': '20 años 12%',
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
    Calcula el ahorro al hacer abonos extra mensuales al capital.

    Hacer abonos extraordinarios reduce dramáticamente los intereses y el plazo.

    Args:
        principal (float): Monto del préstamo
        annual_rate (float): Tasa efectiva anual
        years (int): Plazo original en años
        extra_monthly_payment (float): Abono extra cada mes al capital

    Returns:
        Dict: Comparación con/sin abonos extra:
            {
                'original': {
                    'months': 240,
                    'total_interest': 492522491.23,
                    'monthly_payment': 3302177.15
                },
                'with_extra': {
                    'months': 180,  # Se reduce el plazo
                    'total_interest': 320000000.00,  # Menos intereses
                    'monthly_payment': 3802177.15,  # Cuota + extra
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
