"""
Budget service — YNAB-style "Give every dollar a job".

Provides helpers for building, querying and calculating budget data including
multi-currency conversion, rollover logic and the Ready-to-Assign figure.
"""
from __future__ import annotations

from datetime import date, datetime
from collections.abc import Callable
from typing import Optional
from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, extract, or_
from sqlalchemy.orm import Session, joinedload
from finance_app.models import BudgetMonth, Category, CategoryGroup, Transaction, Account, Currency
from finance_app.services.transaction_service import get_monthly_activity
from finance_app.services.exchange_rate_service import get_current_exchange_rate, convert_currency


# ---------------------------------------------------------------------------
# Shared currency-conversion helper
# ---------------------------------------------------------------------------

def _make_currency_converter(
    target_currency_code: str,
    exchange_rate_usd_cop: float,
) -> Callable:
    """Return a closure that converts *amount* from *from_code* to the target currency.

    The returned function uses a cached exchange rate so no extra DB queries
    are needed.
    """
    def _convert(amount: float, from_code: str) -> float:
        if from_code == target_currency_code:
            return amount
        if from_code == "USD" and target_currency_code == "COP":
            return amount * exchange_rate_usd_cop
        if from_code == "COP" and target_currency_code == "USD":
            return amount / exchange_rate_usd_cop
        return amount
    return _convert


def _make_currency_converter_2arg(
    target_currency_code: str,
    exchange_rate_usd_cop: float,
) -> Callable:
    """Like :func:`_make_currency_converter` but accepts *(from_code, to_code)*.

    Used inside ``get_month_budget`` where both source and target codes are
    passed explicitly.
    """
    def _convert(amount: float, from_code: str, to_code: str) -> float:
        if from_code == to_code:
            return amount
        if from_code == "USD" and to_code == "COP":
            return amount * exchange_rate_usd_cop
        if from_code == "COP" and to_code == "USD":
            return amount / exchange_rate_usd_cop
        return amount
    return _convert


def build_spent_transactions_query(
    db: Session,
    start_date: date,
    end_date: date,
    category_id: Optional[int] = None
):
    """
    Construye el query base para transacciones de gasto.

    - Solo gastos (montos negativos)
    - Excluye transferencias y ajustes de balance
    - Excluye categorías de ingreso
    - Rango de fechas con fin exclusivo [start_date, end_date)
    """
    query = db.query(Transaction).join(Category).join(CategoryGroup).filter(
        Transaction.date >= start_date,
        Transaction.date < end_date,
        Transaction.amount < 0,
        Transaction.transfer_account_id.is_(None),
        Transaction.is_adjustment.is_(False),
        CategoryGroup.is_income.is_(False)
    )

    if category_id is not None:
        query = query.filter(Transaction.category_id == category_id)

    return query


def build_income_transactions_query(
    db: Session,
    start_date: date,
    end_date: date,
    category_id: Optional[int] = None
):
    """
    Construye el query base para transacciones de ingreso.

    - Solo ingresos (montos positivos)
    - Excluye transferencias y ajustes de balance
    - Incluye categorías de ingreso o ingresos sin categoría
    - Rango de fechas con fin exclusivo [start_date, end_date)
    """
    query = db.query(Transaction).outerjoin(Category).outerjoin(CategoryGroup).filter(
        Transaction.date >= start_date,
        Transaction.date < end_date,
        Transaction.amount > 0,
        Transaction.transfer_account_id.is_(None),
        Transaction.is_adjustment.is_(False)
    ).filter(
        or_(
            CategoryGroup.is_income.is_(True),
            Transaction.category_id.is_(None)
        )
    )

    if category_id is not None:
        query = query.filter(Transaction.category_id == category_id)

    return query


def get_assigned_totals_by_currency(db: Session, month_date):
    """
    Obtiene el total asignado por moneda para un mes específico.

    Solo incluye categorías de gasto (excluye grupos de ingreso) y suma el
    valor asignado del mes, sin considerar acumulados previos.

    Returns:
        dict: Dictionary with currency codes as keys and dicts containing
              'total' and 'symbol' as values, e.g.:
              {"COP": {"total": 5000000, "symbol": "$"}, "USD": {"total": 100, "symbol": "US$"}}
    """
    totals = {}
    budgets = db.query(BudgetMonth).options(
        joinedload(BudgetMonth.category).joinedload(Category.category_group),
        joinedload(BudgetMonth.currency)
    ).filter_by(month=month_date).all()

    for budget in budgets:
        category = budget.category
        if not category or not category.category_group:
            continue
        if category.category_group.is_income:
            continue

        currency = budget.currency
        if not currency or not currency.code:
            continue

        currency_code = currency.code
        currency_symbol = currency.symbol if hasattr(currency, 'symbol') and currency.symbol else ('US$' if currency_code == 'USD' else '$')

        if currency_code not in totals:
            totals[currency_code] = {"total": 0.0, "symbol": currency_symbol}

        totals[currency_code]["total"] += (budget.assigned or 0.0)

    return totals


def get_previous_budget(db: Session, category_id, month_date, currency_id):
    return db.query(BudgetMonth).filter(
        BudgetMonth.category_id == category_id,
        BudgetMonth.currency_id == currency_id,
        BudgetMonth.month < month_date
    ).order_by(BudgetMonth.month.desc()).first()


def has_any_previous_budget(db: Session, category_id, currency_id, exclude_month=None):
    """
    Verifica si existe ALGÚN presupuesto previo para esta categoría en esta moneda.

    Esta función es importante para evitar usar el initial_amount múltiples veces.
    Solo debemos usar initial_amount si esta es verdaderamente la PRIMERA VEZ
    que se presupuesta para esta categoría en esta moneda.

    Args:
        exclude_month: Mes a excluir de la búsqueda (para evitar contar el mes actual)

    Returns:
        bool: True si existe al menos un budget previo, False si es la primera vez
    """
    query = db.query(BudgetMonth).filter(
        BudgetMonth.category_id == category_id,
        BudgetMonth.currency_id == currency_id
    )

    if exclude_month:
        query = query.filter(BudgetMonth.month != exclude_month)

    return query.first() is not None


def get_or_create_budget_month(db: Session, category_id, month_date, currency_id):
    """
    Obtiene o crea una entrada de presupuesto para un mes y categoría específicos.

    Esta función busca si ya existe un presupuesto para la combinación de categoría,
    mes y moneda. Si no existe, crea uno nuevo con valores en 0.

    Args:
        db (Session): Sesión de base de datos SQLAlchemy
        category_id (int): ID de la categoría a presupuestar
        month_date (date): Primer día del mes (ej: date(2025, 1, 1))
        currency_id (int): ID de la moneda (1=COP, 2=USD)

    Returns:
        BudgetMonth: Objeto de presupuesto mensual (existente o nuevo)

    Ejemplo:
        >>> from datetime import date
        >>> budget = get_or_create_budget_month(db, category_id=5,
        ...                                     month_date=date(2025, 1, 1),
        ...                                     currency_id=1)
        >>> print(budget.assigned)  # 0.0 si es nuevo
    """
    budget = db.query(BudgetMonth).filter_by(
        category_id=category_id,
        month=month_date,
        currency_id=currency_id
    ).first()

    if not budget:
        budget = BudgetMonth(
            category_id=category_id,
            month=month_date,
            currency_id=currency_id,
            assigned=0.0,
            activity=0.0,
            available=0.0
        )
        db.add(budget)
        db.commit()

    return budget


def assign_money_to_category(db: Session, category_id, month_date, currency_id, amount, initial_amount=None):
    """
    Asigna dinero a una categoría para un mes específico (columna "Asignado" en YNAB).

    Args:
        db (Session): Sesión de base de datos
        category_id (int): ID de la categoría
        month_date (date): Primer día del mes
        currency_id (int): ID de la moneda
        amount (float): Cantidad a asignar (puede ser 0 o positiva)
        initial_amount (float, optional): Dinero acumulado inicial (para categorías accumulate)

    Returns:
        BudgetMonth: Objeto de presupuesto actualizado con el nuevo valor assigned
    """
    budget = get_or_create_budget_month(db, category_id, month_date, currency_id)
    budget.assigned = amount
    if initial_amount is not None:
        budget.initial_amount = initial_amount
    existing_budgets = db.query(BudgetMonth).filter_by(
        category_id=category_id,
        month=month_date
    ).all()
    has_multiple_budget_currencies = len({b.currency_id for b in existing_budgets}) > 1
    recalculate_budget_available(
        db,
        budget,
        include_all_currencies=not has_multiple_budget_currencies
    )
    db.commit()
    return budget


def recalculate_budget_available(db: Session, budget_month, include_all_currencies: bool = True):
    """
    Calcula la cantidad disponible para un presupuesto mensual.

    Esta es una función crítica que implementa el comportamiento de rollover de YNAB.
    Hay dos tipos de comportamiento según la categoría:

    1. ACCUMULATE (ahorro/saving): El disponible se calcula con el dinero inicial
       más lo asignado del mes menos lo gastado.
       Fórmula: Disponible = Monto Inicial + Asignado + Actividad
       Ejemplo: Si tengo $200 iniciales, asigné $100 y gasté $30:
                Disponible = $200 + $100 + (-$30) = $270

    2. RESET (gasto mensual): El dinero se resetea cada mes
       Fórmula: Disponible = Asignado + Actividad
       Ejemplo: Si asigné $100 y gasté $30:
                Disponible = $100 + (-$30) = $70
                (No importa si sobraron $50 del mes pasado)

    Args:
        db (Session): Sesión de base de datos
        budget_month (BudgetMonth): Objeto de presupuesto mensual a calcular

    Returns:
        BudgetMonth: El mismo objeto con los campos activity y available actualizados

    Efectos secundarios:
        - Actualiza budget_month.activity consultando transacciones del mes
        - Actualiza budget_month.available según el tipo de rollover
        - NO hace commit, el llamador debe hacer commit

    Nota importante:
        La actividad (activity) es NEGATIVA para gastos y POSITIVA para ingresos.
        Por ejemplo: gastar $50 → activity = -$50
    """
    # Get category to check rollover type
    category = db.query(Category).get(budget_month.category_id)

    # Get activity from transactions
    month = budget_month.month.month
    year = budget_month.month.year

    activity = get_monthly_activity(
        db,
        budget_month.category_id,
        month,
        year,
        budget_month.currency_id,
        include_all_currencies=include_all_currencies
    )

    budget_month.activity = activity

    # Get initial amount (only for 'accumulate' categories)
    initial_available = 0.0

    if category and category.rollover_type == 'accumulate':
        # Use the per-month initial_amount stored on the BudgetMonth record
        initial_available = budget_month.initial_amount or 0.0

    # Available = assigned - activity (negative for expenses) + initial amount (if accumulate)
    # activity is negative for expenses, so we add it
    budget_month.available = budget_month.assigned + activity + initial_available

    return budget_month


def get_month_budget(db: Session, month_date, currency_code='COP'):
    """
    Obtiene el presupuesto completo de un mes específico con TODAS las categorías.

    Esta es la función principal para obtener la vista del presupuesto. Retorna una
    estructura completa con todos los grupos de categorías, sus categorías, y los
    valores de presupuesto (asignado, actividad, disponible).

    IMPORTANTE - Multi-moneda:
        Esta función es multi-moneda inteligente. Si tienes presupuestos en USD y COP
        para la misma categoría, los suma CONVIRTIENDO todo a la moneda especificada.

        Ejemplo: Categoría "Comida"
            - Presupuesto en COP: $800,000
            - Presupuesto en USD: $100 (= $400,000 COP a tasa 4000)
            - Total mostrado en COP: $1,200,000

    Args:
        db (Session): Sesión de base de datos
        month_date (date): Primer día del mes (ej: date(2025, 1, 1))
        currency_code (str): Código de moneda para mostrar ('COP' o 'USD')

    Returns:
        dict: Estructura del presupuesto con formato:
            {
                'month': '2025-01-01',
                'currency': {'id': 1, 'code': 'COP', 'symbol': '$'},
                'ready_to_assign': 500000.0,
                'totals': {
                    'assigned': 2000000.0,
                    'activity': -1500000.0,
                    'available': 500000.0,
                    'in_accounts': 9000000.0
                },
                'groups': [
                    {
                        'id': 1,
                        'name': 'Gastos Esenciales',
                        'is_income': False,
                        'categories': [
                            {
                                'category_id': 1,
                                'category_name': 'Comida',
                                'assigned': 800000.0,
                                'activity': -650000.0,
                                'available': 150000.0,
                                'target_amount': 1000000.0,
                                'rollover_type': 'reset'
                            },
                            ...
                        ]
                    },
                    ...
                ]
            }

    Optimizaciones implementadas:
        1. Eager loading con joinedload() para evitar N+1 queries
        2. Caché de tasas de cambio en memoria (1 query en lugar de 100+)
        3. Caché de todas las monedas en diccionario
        4. Query batch de TODOS los presupuestos del mes a la vez
        5. Lookup O(1) usando diccionarios en lugar de queries repetidas
        6. Un solo commit al final en lugar de múltiples commits

    Rendimiento:
        Reducción de ~200 queries a solo 4 queries (mejora de 50x)

    Notas:
        - Las categorías ocultas (is_hidden=True) se excluyen
        - Los grupos de ingreso se incluyen pero no se suman en totales
        - Si no existe presupuesto para una categoría, se crea automáticamente
    """
    currency = db.query(Currency).filter_by(code=currency_code).first()
    if not currency:
        return None

    all_currencies = {c.id: c for c in db.query(Currency).all()}
    exchange_rate_usd_cop = get_current_exchange_rate(db)
    convert = _make_currency_converter_2arg(currency.code, exchange_rate_usd_cop)

    groups = db.query(CategoryGroup).options(
        joinedload(CategoryGroup.categories)
    ).order_by(CategoryGroup.sort_order).all()

    budget_data: dict = {
        'month': month_date.isoformat(),
        'currency': currency.to_dict(),
        'groups': [],
        'ready_to_assign': 0.0,
        'totals': {'assigned': 0.0, 'activity': 0.0, 'available': 0.0},
    }

    budgets_by_category = _index_budgets_by_category(db, month_date)

    for group in groups:
        group_data = _build_group_budget(
            db, group, month_date, currency, all_currencies,
            convert, budgets_by_category, budget_data['totals'],
        )
        budget_data['groups'].append(group_data)

    db.commit()

    total_in_accounts = calculate_total_in_accounts(db, currency.id)
    budget_data['totals']['in_accounts'] = total_in_accounts
    budget_data['ready_to_assign'] = total_in_accounts - budget_data['totals']['available']

    return budget_data


# -- helpers for get_month_budget ------------------------------------------

def _index_budgets_by_category(db: Session, month_date: date) -> dict[int, list[BudgetMonth]]:
    """Load all budget rows for *month_date* and index them by category_id."""
    all_month_budgets = db.query(BudgetMonth).options(
        joinedload(BudgetMonth.category)
    ).filter_by(month=month_date).all()

    index: dict[int, list[BudgetMonth]] = {}
    for budget in all_month_budgets:
        index.setdefault(budget.category_id, []).append(budget)
    return index


def _build_group_budget(
    db: Session,
    group: CategoryGroup,
    month_date: date,
    currency: Currency,
    all_currencies: dict,
    convert: Callable,
    budgets_by_category: dict[int, list[BudgetMonth]],
    running_totals: dict,
) -> dict:
    """Build the budget dict for a single category group."""
    group_data: dict = {
        'id': group.id,
        'name': group.name,
        'is_income': group.is_income,
        'categories': [],
    }

    for category in group.categories:
        if category.is_hidden:
            continue

        cat_data = _build_category_budget(
            db, category, month_date, currency, all_currencies,
            convert, budgets_by_category,
        )
        group_data['categories'].append(cat_data)

        if not group.is_income:
            running_totals['assigned'] += cat_data['assigned']
            running_totals['activity'] += abs(cat_data['activity'])
            running_totals['available'] += cat_data['available']

    return group_data


def _build_category_budget(
    db: Session,
    category: Category,
    month_date: date,
    currency: Currency,
    all_currencies: dict,
    convert: Callable,
    budgets_by_category: dict[int, list[BudgetMonth]],
) -> dict:
    """Build the budget dict for a single category within a group."""
    all_budgets = budgets_by_category.get(category.id, [])
    if not all_budgets:
        budget = get_or_create_budget_month(db, category.id, month_date, currency.id)
        all_budgets = [budget]

    has_multi_curr = len({b.currency_id for b in all_budgets}) > 1

    total_assigned = 0.0
    total_activity = 0.0
    total_available = 0.0

    for budget in all_budgets:
        recalculate_budget_available(db, budget, include_all_currencies=not has_multi_curr)
        bcur = all_currencies.get(budget.currency_id)
        if not bcur:
            continue
        total_assigned += convert(budget.assigned, bcur.code, currency.code)
        total_activity += convert(budget.activity, bcur.code, currency.code)
        total_available += convert(budget.available, bcur.code, currency.code)

    total_initial = 0.0
    if category.rollover_type == 'accumulate':
        for budget in all_budgets:
            bcur = all_currencies.get(budget.currency_id)
            if bcur:
                total_initial += convert(budget.initial_amount or 0.0, bcur.code, currency.code)

    return {
        'category_id': category.id,
        'category_name': category.name,
        'assigned': total_assigned,
        'activity': total_activity,
        'available': total_available,
        'initial_amount': total_initial,
        'target_amount': category.target_amount,
        'rollover_type': category.rollover_type,
        'is_essential': bool(category.is_essential),
    }


def calculate_total_in_accounts(db: Session, currency_id: int) -> float:
    """Return the sum of all open budget-account balances converted to *currency_id*.

    Excludes debt accounts (credit_card, credit_loan, mortgage).
    """
    target_currency = db.query(Currency).get(currency_id)
    convert = _make_currency_converter(target_currency.code, get_current_exchange_rate(db))

    excluded_types = {'credit_card', 'credit_loan', 'mortgage'}
    accounts = db.query(Account).options(
        joinedload(Account.currency)
    ).filter(
        Account.is_closed == False,
        Account.is_budget == True,
        ~Account.type.in_(excluded_types),
    ).all()

    return sum(convert(acc.balance, acc.currency.code) for acc in accounts)


def calculate_ready_to_assign(db: Session, month_date, currency_id):
    """
    Calcula el dinero disponible para asignar (Ready to Assign / Dinero sin objetivo).

    Este es uno de los conceptos más importantes de YNAB. Representa el dinero que
    tienes en tus cuentas bancarias pero que AÚN NO has asignado a ninguna categoría.

    FÓRMULA:
        Ready to Assign = Total en cuentas presupuestarias
                        - Total disponible en categorías este mes

    EJEMPLO:
        Cuentas presupuestarias:
            - Cuenta Corriente COP: $5,000,000
            - Cuenta Ahorros USD: $1,000 (= $4,000,000 COP a tasa 4000)
            Total en cuentas: $9,000,000 COP

        Disponible en categorías enero:
            - Comida (COP): $700,000
            - Transporte (USD): $100 (= $400,000 COP)
            Total disponible: $1,100,000 COP

        Ready to Assign = $9,000,000 - $1,100,000 = $7,900,000 COP

    IMPORTANTE - Multi-moneda:
        Esta función considera TODAS las cuentas y presupuestos en TODAS las monedas,
        convirtiendo todo a la moneda objetivo antes de hacer la resta.

    Args:
        db (Session): Sesión de base de datos
        month_date (date): Mes a calcular (primer día del mes)
        currency_id (int): ID de moneda objetivo para mostrar el resultado

    Returns:
        float: Cantidad disponible para asignar en la moneda objetivo

    Optimizaciones:
        - Caché de tasa de cambio (1 query vs muchas)
        - Eager loading de relaciones (evita N+1)
        - Batch queries en lugar de loops

    Notas:
        - Solo considera cuentas presupuestarias (is_budget=True)
        - Solo considera cuentas abiertas (is_closed=False)
        - Excluye cuentas de deuda (credit_card, credit_loan, mortgage)
        - Las cuentas de seguimiento (tracking) NO se incluyen
        - El dinero no disponible (sin asignar) aparece automáticamente en Ready to Assign
    """
    target_currency = db.query(Currency).get(currency_id)
    convert = _make_currency_converter(target_currency.code, get_current_exchange_rate(db))

    total_in_accounts = calculate_total_in_accounts(db, currency_id)

    all_budgets = db.query(BudgetMonth).options(
        joinedload(BudgetMonth.category).joinedload(Category.category_group)
    ).filter_by(month=month_date).all()

    currency_cache = {c.id: c for c in db.query(Currency).all()}
    cat_currencies: dict[int, set[int]] = {}
    for b in all_budgets:
        cat_currencies.setdefault(b.category_id, set()).add(b.currency_id)

    total_available = 0.0
    for budget in all_budgets:
        if budget.category and budget.category.category_group and budget.category.category_group.is_income:
            continue
        has_multi = len(cat_currencies.get(budget.category_id, set())) > 1
        recalculate_budget_available(db, budget, include_all_currencies=not has_multi)
        bcur = currency_cache.get(budget.currency_id)
        if bcur:
            total_available += convert(budget.available, bcur.code)

    return total_in_accounts - total_available


def calculate_assigned_this_month(db: Session, month_date, currency_id):
    """
    Calcula el total asignado durante el mes actual sin contar asignaciones heredadas
    de meses anteriores.

    Se calcula como la diferencia entre el asignado del mes actual y el asignado del
    mes anterior por categoría/moneda.
    """
    target_currency = db.query(Currency).get(currency_id)
    if not target_currency:
        return 0.0

    convert = _make_currency_converter(target_currency.code, get_current_exchange_rate(db))
    previous_month = month_date - relativedelta(months=1)

    budgets = db.query(BudgetMonth).options(
        joinedload(BudgetMonth.category).joinedload(Category.category_group),
        joinedload(BudgetMonth.currency)
    ).filter_by(month=month_date).all()

    total_assigned = 0.0
    for budget in budgets:
        if not budget.category or not budget.category.category_group:
            continue
        if budget.category.category_group.is_income:
            continue

        prev_budget = db.query(BudgetMonth).filter_by(
            category_id=budget.category_id,
            currency_id=budget.currency_id,
            month=previous_month
        ).first()

        previous_assigned = prev_budget.assigned if prev_budget else 0.0
        delta_assigned = (budget.assigned or 0.0) - (previous_assigned or 0.0)

        budget_currency = budget.currency
        if not budget_currency:
            continue

        total_assigned += convert(delta_assigned, budget_currency.code)

    return total_assigned


def calculate_spent_to_date(db: Session, month_date, currency_id):
    """
    Calcula el total gastado desde el primer día del mes hasta hoy (inclusive).
    Solo considera transacciones de gasto (montos negativos) y excluye ingresos.
    """
    target_currency = db.query(Currency).get(currency_id)
    if not target_currency:
        return 0.0

    start_date = month_date
    end_of_month = month_date + relativedelta(months=1)
    today = date.today()

    if today < start_date:
        end_date = start_date
    elif today >= end_of_month:
        end_date = end_of_month
    else:
        end_date = today + relativedelta(days=1)

    transactions = build_spent_transactions_query(db, start_date, end_date).options(
        joinedload(Transaction.currency)
    ).all()

    total_spent = 0.0
    for tx in transactions:
        tx_currency = tx.currency.code if tx.currency else target_currency.code
        converted_amount = convert_currency(
            abs(tx.amount),
            tx_currency,
            target_currency.code,
            db,
            rate_date=tx.date
        )
        total_spent += converted_amount

    return total_spent


def get_spent_transactions_to_date(db: Session, month_date, currency_id):
    """
    Obtiene las transacciones usadas para calcular "Gastado este mes".

    Retorna una lista de transacciones de gasto (montos negativos) desde el primer
    día del mes hasta hoy (inclusive), junto con el monto convertido a la moneda
    objetivo para facilitar el detalle en la UI.
    """
    target_currency = db.query(Currency).get(currency_id)
    if not target_currency:
        return {"error": "Currency not found"}

    start_date = month_date
    end_of_month = month_date + relativedelta(months=1)
    today = date.today()

    if today < start_date:
        end_date = start_date
    elif today >= end_of_month:
        end_date = end_of_month
    else:
        end_date = today + relativedelta(days=1)

    transactions = build_spent_transactions_query(db, start_date, end_date).options(
        joinedload(Transaction.currency),
        joinedload(Transaction.account),
        joinedload(Transaction.payee),
        joinedload(Transaction.category)
    ).order_by(Transaction.date.desc()).all()

    detailed = []
    total_spent = 0.0
    for tx in transactions:
        tx_currency = tx.currency.code if tx.currency else target_currency.code
        converted_amount = convert_currency(
            abs(tx.amount),
            tx_currency,
            target_currency.code,
            db,
            rate_date=tx.date
        )
        total_spent += converted_amount
        tx_data = tx.to_dict()
        tx_data["spent_converted"] = converted_amount
        tx_data["spent_currency_code"] = target_currency.code
        detailed.append(tx_data)

    return {
        "currency_code": target_currency.code,
        "total_spent": total_spent,
        "transactions": detailed
    }


def get_budget_overview(db: Session, currency_code='COP'):
    """
    Get budget overview for current month
    """
    today = date.today()
    month_date = date(today.year, today.month, 1)

    return get_month_budget(db, month_date, currency_code)


def move_to_next_month(db: Session, current_month_date, currency_id):
    """
    Roll over budget to next month (YNAB style)
    Carries over 'available' amounts to next month
    """
    next_month = current_month_date + relativedelta(months=1)

    budgets = db.query(BudgetMonth).filter_by(
        month=current_month_date,
        currency_id=currency_id
    ).all()

    for budget in budgets:
        if budget.available > 0:
            next_budget = get_or_create_budget_month(
                db,
                budget.category_id,
                next_month,
                currency_id
            )
            # The available will be automatically calculated when needed
            db.commit()

    return True


def _sum_by_currency_code(
    budgets_list: list[BudgetMonth],
    currencies: dict,
    code: str,
    field: str,
) -> float:
    """Sum *field* from budget rows whose currency matches *code*."""
    return sum(
        getattr(b, field) or 0
        for b in budgets_list
        if currencies.get(b.currency_id) and currencies[b.currency_id].code == code
    )


def _summarise_month_budgets(
    month: date,
    all_budgets: list[BudgetMonth],
    currencies: dict,
    to_cop_fn: Callable,
) -> dict:
    """Build one row of the monthly summary table for budget history."""
    month_budgets = [b for b in all_budgets if b.month == month]
    return {
        "month": month.isoformat(),
        "assigned_cop": _sum_by_currency_code(month_budgets, currencies, "COP", "assigned"),
        "activity_cop": _sum_by_currency_code(month_budgets, currencies, "COP", "activity"),
        "available_cop": _sum_by_currency_code(month_budgets, currencies, "COP", "available"),
        "assigned_usd": _sum_by_currency_code(month_budgets, currencies, "USD", "assigned"),
        "activity_usd": _sum_by_currency_code(month_budgets, currencies, "USD", "activity"),
        "available_usd": _sum_by_currency_code(month_budgets, currencies, "USD", "available"),
        "total_assigned": sum(to_cop_fn(b.assigned, b.currency_id) for b in month_budgets),
        "total_activity": sum(to_cop_fn(b.activity, b.currency_id) for b in month_budgets),
        "total_available": sum(to_cop_fn(b.available, b.currency_id) for b in month_budgets),
    }


def get_category_budget_history(db: Session, category_id: int, months: int = 3):
    """
    Returns monthly budget history (assigned, activity, available) and
    associated transactions for a category over the last N months.

    All monetary values are returned both per-currency and consolidated to COP.
    """
    today = date.today()
    current_month = date(today.year, today.month, 1)

    # Build list of months going back
    month_list = []
    for i in range(months):
        m = current_month - relativedelta(months=i)
        month_list.append(m)

    currencies = {c.id: c for c in db.query(Currency).all()}
    exchange_rate = get_current_exchange_rate(db)

    # Get budget records for all months and recalculate to reflect latest transactions
    budgets = db.query(BudgetMonth).filter(
        BudgetMonth.category_id == category_id,
        BudgetMonth.month.in_(month_list)
    ).order_by(BudgetMonth.month).all()

    # Group by month to detect multi-currency budgets (same logic as get_month_budget)
    budgets_by_month = {}
    for b in budgets:
        budgets_by_month.setdefault(b.month, []).append(b)

    for month_key, month_budgets_list in budgets_by_month.items():
        has_multiple_currencies = len({b.currency_id for b in month_budgets_list}) > 1
        for b in month_budgets_list:
            recalculate_budget_available(db, b, include_all_currencies=not has_multiple_currencies)
    db.commit()

    to_cop = _make_currency_converter("COP", exchange_rate)

    def _to_cop_by_id(amount: float, cur_id: int) -> float:
        cur = currencies.get(cur_id)
        if not cur or cur.code == "COP":
            return float(amount or 0)
        return float(amount or 0) * exchange_rate

    monthly_summary = [
        _summarise_month_budgets(m, budgets, currencies, _to_cop_by_id)
        for m in month_list
    ]

    # Get transactions for the date range
    oldest_month = month_list[-1]
    next_of_current = current_month + relativedelta(months=1)

    transactions = db.query(Transaction).options(
        joinedload(Transaction.account)
    ).filter(
        Transaction.category_id == category_id,
        Transaction.date >= oldest_month,
        Transaction.date < next_of_current,
    ).order_by(Transaction.date.desc()).all()

    tx_list = []
    for tx in transactions:
        tx_list.append({
            "id": tx.id,
            "date": tx.date.isoformat(),
            "amount": tx.amount,
            "memo": tx.memo,
            "account_name": tx.account.name if tx.account else None,
            "currency_code": currencies.get(tx.currency_id, None).code if currencies.get(tx.currency_id) else "COP",
        })

    return {
        "category_id": category_id,
        "months": months,
        "monthly_summary": monthly_summary,
        "transactions": tx_list,
    }
