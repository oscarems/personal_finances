# Arquitectura del Sistema - Guía Completa

Esta guía explica detalladamente dónde está cada componente del sistema y cómo funcionan juntos.

## 📁 Estructura de Directorios

```
personal_finances/
├── backend/                    # Todo el código del servidor
│   ├── models/                # Modelos de base de datos (SQLAlchemy)
│   │   ├── __init__.py       # Exporta todos los modelos
│   │   ├── account.py        # Modelo de cuentas bancarias
│   │   ├── budget.py         # Modelo de presupuestos mensuales
│   │   ├── category.py       # Modelo de categorías y grupos
│   │   ├── currency.py       # Modelo de monedas (COP, USD)
│   │   ├── exchange_rate.py  # Modelo de tasas de cambio históricas
│   │   ├── payee.py          # Modelo de beneficiarios/comercios
│   │   ├── recurring_transaction.py  # Transacciones recurrentes
│   │   └── transaction.py    # Modelo de transacciones
│   │
│   ├── services/             # Lógica de negocio
│   │   ├── budget_service.py         # Cálculos de presupuesto
│   │   ├── exchange_rate_service.py  # Obtener tasas de cambio
│   │   ├── import_service.py         # Importar datos de YNAB
│   │   ├── mortgage_service.py       # Simulador de hipotecas
│   │   ├── report_service.py         # Generación de reportes
│   │   └── transaction_service.py    # Lógica de transacciones
│   │
│   ├── api/                  # Endpoints REST de la API
│   │   ├── accounts.py       # GET/POST/PUT/DELETE cuentas
│   │   ├── budgets.py        # GET/POST presupuestos
│   │   ├── categories.py     # GET/POST/PUT categorías
│   │   ├── exchange_rates.py # GET tasas de cambio
│   │   ├── import_routes.py  # POST importar YNAB
│   │   ├── mortgage.py       # POST calcular hipoteca
│   │   ├── recurring.py      # GET/POST transacciones recurrentes
│   │   ├── reports.py        # GET reportes
│   │   └── transactions.py   # GET/POST/DELETE transacciones
│   │
│   ├── app.py                # Aplicación FastAPI principal
│   ├── database.py           # Configuración de SQLAlchemy
│   └── init_db.py            # Script para crear base de datos
│
├── frontend/                 # Todo el código del cliente
│   ├── templates/            # Plantillas HTML (Jinja2)
│   │   ├── accounts.html     # Página de cuentas
│   │   ├── budget.html       # Página de presupuesto
│   │   ├── categories.html   # Página de categorías
│   │   ├── dashboard.html    # Página principal
│   │   ├── import.html       # Página de importación YNAB
│   │   ├── layout.html       # Layout base (header, nav)
│   │   ├── mortgage.html     # Simulador de hipotecas
│   │   ├── recurring.html    # Transacciones recurrentes
│   │   ├── reports.html      # Reportes
│   │   └── transactions.html # Página de transacciones
│   │
│   └── static/               # Archivos estáticos (CSS, JS, imágenes)
│       └── styles.css        # Estilos personalizados
│
├── data/                     # Base de datos SQLite
│   └── finances.db           # Archivo de base de datos
│
├── config.py                 # Configuración global (tipos de cuenta, APIs)
├── requirements.txt          # Dependencias de Python
├── README.md                 # Documentación principal
├── TUTORIAL.md               # Tutorial de uso
├── YNAB_FEATURES_COMPARISON.md  # Comparación con YNAB
└── ARCHITECTURE.md           # Este archivo

```

---

## 🏗️ Arquitectura Backend (3 Capas)

El backend sigue una arquitectura de 3 capas bien definida:

### Capa 1: Modelos (Models) - `backend/models/`

**Propósito**: Definir la estructura de la base de datos usando SQLAlchemy ORM.

**Patrón**: Cada modelo es una clase que hereda de `Base` y representa una tabla.

#### Archivos clave:

**`backend/models/__init__.py`**
```python
# Exporta TODOS los modelos para que SQLAlchemy los registre
from backend.models.currency import Currency
from backend.models.account import Account
from backend.models.category import CategoryGroup, Category
from backend.models.payee import Payee
from backend.models.transaction import Transaction
from backend.models.budget import BudgetMonth
from backend.models.recurring_transaction import RecurringTransaction
from backend.models.exchange_rate import ExchangeRate

__all__ = [
    'Currency', 'Account', 'CategoryGroup', 'Category',
    'Payee', 'Transaction', 'BudgetMonth',
    'RecurringTransaction', 'ExchangeRate'
]
```

**`backend/models/account.py`** - Modelo de cuentas
```python
class Account(Base):
    __tablename__ = 'accounts'

    # Campos básicos
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    type = Column(String(50), nullable=False)  # checking, savings, credit_card, etc.
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=False)
    balance = Column(Float, default=0.0)

    # Campos opcionales según tipo de cuenta
    interest_rate = Column(Float)        # Para savings, loans, CDT
    credit_limit = Column(Float)         # Para credit cards
    monthly_payment = Column(Float)      # Para loans, mortgage
    original_amount = Column(Float)      # Para loans, mortgage, CDT
    payment_due_day = Column(Integer)    # Día del mes (1-31)
    maturity_date = Column(Date)         # Para CDT

    # Relaciones
    currency = relationship("Currency", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")
```

**`backend/models/transaction.py`** - Modelo de transacciones
```python
class Transaction(Base):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    date = Column(Date, nullable=False, index=True)
    payee_id = Column(Integer, ForeignKey('payees.id'))
    category_id = Column(Integer, ForeignKey('categories.id'))
    memo = Column(String(500))
    amount = Column(Float, nullable=False)
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=False)

    # Campos especiales
    cleared = Column(Boolean, default=False)
    approved = Column(Boolean, default=True)
    transfer_account_id = Column(Integer, ForeignKey('accounts.id'))  # Para transferencias

    # Relaciones
    account = relationship("Account", foreign_keys=[account_id], back_populates="transactions")
    payee = relationship("Payee", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")
    currency = relationship("Currency")
```

**`backend/models/budget.py`** - Modelo de presupuestos
```python
class BudgetMonth(Base):
    __tablename__ = 'budget_months'

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=False)
    month = Column(Date, nullable=False, index=True)  # Primer día del mes
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=False)

    # Valores del presupuesto
    assigned = Column(Float, default=0.0)    # Lo que asignaste
    activity = Column(Float, default=0.0)    # Lo que gastaste
    available = Column(Float, default=0.0)   # Lo que queda

    # Relaciones
    category = relationship("Category", back_populates="budgets")
    currency = relationship("Currency")
```

**`backend/models/exchange_rate.py`** - Tasas de cambio históricas
```python
class ExchangeRate(Base):
    __tablename__ = 'exchange_rates'

    id = Column(Integer, primary_key=True)
    from_currency = Column(String(3), nullable=False, index=True)  # USD
    to_currency = Column(String(3), nullable=False, index=True)    # COP
    rate = Column(Float, nullable=False)  # 1 USD = X COP
    date = Column(Date, nullable=False, unique=True, index=True)
    source = Column(String(50))  # 'api_primary', 'api_fallback', 'average', 'manual'
    created_at = Column(DateTime, default=datetime.utcnow)
```

---

### Capa 2: Servicios (Services) - `backend/services/`

**Propósito**: Contener toda la lógica de negocio. Los servicios NO manejan HTTP, solo lógica pura.

**Patrón**: Funciones que reciben `db: Session` y parámetros, devuelven datos procesados.

#### Archivos clave:

**`backend/services/budget_service.py`** - Lógica de presupuesto
```python
def get_month_budget(db: Session, month_date, currency_code='COP'):
    """
    Obtiene el presupuesto completo de un mes específico.

    Args:
        db: Sesión de base de datos
        month_date: Fecha del mes (ej: '2025-01-01')
        currency_code: Moneda para mostrar ('COP' o 'USD')

    Returns:
        dict: Estructura completa del presupuesto con grupos, categorías, y totales

    Optimizaciones:
        - Usa joinedload() para evitar N+1 queries
        - Cachea tasas de cambio en memoria
        - Hace queries batch en lugar de loops
        - Un solo commit al final
    """
    # 1. Obtener moneda objetivo y cachear todas las monedas
    currency = db.query(Currency).filter_by(code=currency_code).first()
    all_currencies = {c.id: c for c in db.query(Currency).all()}

    # 2. Obtener tasa de cambio actual y cachearla
    exchange_rate_usd_cop = get_current_exchange_rate(db)

    # 3. Helper para conversión usando caché
    def convert_with_cache(amount, from_code, to_code):
        if from_code == to_code:
            return amount
        if from_code == 'USD' and to_code == 'COP':
            return amount * exchange_rate_usd_cop
        elif from_code == 'COP' and to_code == 'USD':
            return amount / exchange_rate_usd_cop
        return amount

    # 4. Eager loading de grupos con categorías (evita N+1)
    groups = db.query(CategoryGroup).options(
        joinedload(CategoryGroup.categories)
    ).order_by(CategoryGroup.sort_order).all()

    # 5. Batch query de TODOS los presupuestos del mes
    all_month_budgets = db.query(BudgetMonth).options(
        joinedload(BudgetMonth.category)
    ).filter_by(month=month_date).all()

    # 6. Crear diccionario para lookup O(1)
    budgets_by_category = {}
    for budget in all_month_budgets:
        if budget.category_id not in budgets_by_category:
            budgets_by_category[budget.category_id] = []
        budgets_by_category[budget.category_id].append(budget)

    # 7. Procesar cada categoría
    budget_data = {
        'groups': [],
        'ready_to_assign': calculate_ready_to_assign(db, month_date, currency.id),
        'currency': currency.to_dict()
    }

    for group in groups:
        group_data = {
            'id': group.id,
            'name': group.name,
            'categories': []
        }

        for category in group.categories:
            # Obtener presupuestos de TODAS las monedas para esta categoría
            all_budgets = budgets_by_category.get(category.id, [])

            # Sumar todo convirtiendo a moneda objetivo
            total_assigned = 0.0
            total_activity = 0.0
            total_available = 0.0

            for budget in all_budgets:
                calculate_available(db, budget)
                budget_currency = all_currencies.get(budget.currency_id)

                total_assigned += convert_with_cache(
                    budget.assigned, budget_currency.code, currency.code
                )
                total_activity += convert_with_cache(
                    budget.activity, budget_currency.code, currency.code
                )
                total_available += convert_with_cache(
                    budget.available, budget_currency.code, currency.code
                )

            category_data = {
                'id': category.id,
                'name': category.name,
                'assigned': total_assigned,
                'activity': total_activity,
                'available': total_available
            }
            group_data['categories'].append(category_data)

        budget_data['groups'].append(group_data)

    # 8. Un solo commit al final
    db.commit()
    return budget_data


def calculate_ready_to_assign(db: Session, month_date, currency_id):
    """
    Calcula dinero disponible para asignar (dinero sin objetivo).

    Fórmula:
        Ready to Assign = Total en TODAS las cuentas (convertido)
                        - Total asignado en TODAS las monedas (convertido)
                        + Rollover de categorías que resetean

    Args:
        db: Sesión de base de datos
        month_date: Mes a calcular
        currency_id: ID de moneda objetivo

    Returns:
        float: Cantidad disponible para asignar
    """
    target_currency = db.query(Currency).get(currency_id)
    exchange_rate = get_current_exchange_rate(db)

    # Helper de conversión
    def convert(amount, from_code):
        if from_code == target_currency.code:
            return amount
        if from_code == 'USD' and target_currency.code == 'COP':
            return amount * exchange_rate
        elif from_code == 'COP' and target_currency.code == 'USD':
            return amount / exchange_rate
        return amount

    # 1. Total en TODAS las cuentas presupuestarias
    all_accounts = db.query(Account).options(
        joinedload(Account.currency)
    ).filter_by(is_closed=False, is_budget=True).all()

    total_in_accounts = sum(
        convert(acc.balance, acc.currency.code)
        for acc in all_accounts
    )

    # 2. Total asignado este mes en TODAS las monedas
    all_budgets = db.query(BudgetMonth).filter_by(month=month_date).all()
    currency_cache = {c.id: c for c in db.query(Currency).all()}

    total_assigned = sum(
        convert(b.assigned, currency_cache[b.currency_id].code)
        for b in all_budgets
    )

    # 3. Rollover de categorías que resetean
    rollover = 0.0  # Calcular según comportamiento de categorías

    return total_in_accounts - total_assigned + rollover
```

**`backend/services/exchange_rate_service.py`** - Tasas de cambio
```python
def get_current_exchange_rate(db: Session, force_fetch: bool = False) -> float:
    """
    Obtiene la tasa de cambio USD->COP actual con fallback inteligente.

    Estrategia de 5 niveles:
        1. ¿Existe tasa para hoy en DB? → Usarla (a menos que force_fetch=True)
        2. Intentar API primaria 2 veces
        3. Intentar API fallback 2 veces
        4. Promedio de últimas 5 tasas en DB
        5. Valor por defecto: 4000

    Args:
        db: Sesión de base de datos
        force_fetch: Forzar consulta a API ignorando caché de hoy

    Returns:
        float: Tasa USD->COP (ej: 3850.50)
    """
    config = EXCHANGE_RATE_API
    today = date.today()

    # Nivel 1: Verificar si existe para hoy
    if not force_fetch:
        existing = db.query(ExchangeRate).filter(
            ExchangeRate.date == today,
            ExchangeRate.from_currency == 'USD',
            ExchangeRate.to_currency == 'COP'
        ).first()

        if existing:
            print(f"✓ Using cached rate for {today}: {existing.rate}")
            return existing.rate

    # Nivel 2: Intentar API primaria
    for attempt in range(config['retries']):
        rate = fetch_rate_from_api(config['primary'], 'COP')
        if rate:
            save_rate_to_db(db, rate, today, 'api_primary')
            print(f"✓ Fetched from primary API: {rate}")
            return rate
        time.sleep(0.5)

    # Nivel 3: Intentar API fallback
    for attempt in range(config['retries']):
        rate = fetch_rate_from_api(config['fallback'], 'COP')
        if rate:
            save_rate_to_db(db, rate, today, 'api_fallback')
            print(f"✓ Fetched from fallback API: {rate}")
            return rate
        time.sleep(0.5)

    # Nivel 4: Promedio de últimas 5 tasas
    avg_rate = get_average_recent_rates(db, config['fallback_average_days'])
    if avg_rate:
        print(f"⚠ Using 5-day average: {avg_rate}")
        return avg_rate

    # Nivel 5: Valor por defecto
    print(f"⚠ Using default rate: {config['default_rate']}")
    return config['default_rate']


def convert_currency(amount: float, from_currency: str, to_currency: str,
                     db: Session, rate_date: Optional[date] = None) -> float:
    """
    Convierte una cantidad entre monedas.

    Args:
        amount: Cantidad a convertir
        from_currency: Moneda origen ('USD' o 'COP')
        to_currency: Moneda destino ('USD' o 'COP')
        db: Sesión de base de datos
        rate_date: Fecha histórica para tasa (None = usar actual)

    Returns:
        float: Cantidad convertida
    """
    if from_currency == to_currency:
        return amount

    # Obtener tasa (actual o histórica)
    if rate_date:
        rate = get_historical_rate(db, rate_date)
    else:
        rate = get_current_exchange_rate(db)

    # Convertir
    if from_currency == 'USD' and to_currency == 'COP':
        return amount * rate
    elif from_currency == 'COP' and to_currency == 'USD':
        return amount / rate

    return amount
```

**`backend/services/transaction_service.py`** - Transacciones y transferencias
```python
def create_transfer(db: Session, data: dict):
    """
    Crea una transferencia entre dos cuentas.

    Una transferencia son realmente 2 transacciones vinculadas:
        - Transacción 1: Salida (negativa) de cuenta origen
        - Transacción 2: Entrada (positiva) a cuenta destino

    Ambas tienen transfer_account_id apuntando a la otra cuenta.

    Args:
        db: Sesión de base de datos
        data: dict con from_account_id, to_account_id, amount, date, etc.

    Returns:
        list: [transacción_salida, transacción_entrada]

    Soporta:
        - Transferencias entre misma moneda (cantidad igual)
        - Transferencias multi-moneda (con conversión automática)
    """
    # 1. Validar cuentas
    from_account = db.query(Account).get(data['from_account_id'])
    to_account = db.query(Account).get(data['to_account_id'])

    if not from_account or not to_account:
        raise ValueError("Una o ambas cuentas no existen")

    if from_account.id == to_account.id:
        raise ValueError("No se puede transferir a la misma cuenta")

    # 2. Obtener monedas
    from_currency = db.query(Currency).get(data['from_currency_id'])
    to_currency = db.query(Currency).get(data['to_currency_id'])

    # 3. Calcular montos
    from_amount = -abs(data['amount'])  # Negativo (salida)

    # Si son monedas diferentes, convertir
    if from_currency.code != to_currency.code:
        to_amount = convert_currency(
            abs(data['amount']),
            from_currency.code,
            to_currency.code,
            db
        )
    else:
        to_amount = abs(data['amount'])

    # 4. Crear payees para la transferencia
    payee_from = get_or_create_payee(db, f"Transfer to: {to_account.name}")
    payee_to = get_or_create_payee(db, f"Transfer from: {from_account.name}")

    # 5. Crear transacción de SALIDA
    from_transaction = Transaction(
        account_id=data['from_account_id'],
        date=data.get('date', date.today()),
        payee_id=payee_from.id,
        category_id=None,  # Transferencias no tienen categoría
        memo=data.get('memo', ''),
        amount=from_amount,
        currency_id=data['from_currency_id'],
        cleared=data.get('cleared', False),
        approved=True,
        transfer_account_id=data['to_account_id']  # Vincula con cuenta destino
    )

    # 6. Crear transacción de ENTRADA
    to_transaction = Transaction(
        account_id=data['to_account_id'],
        date=data.get('date', date.today()),
        payee_id=payee_to.id,
        category_id=None,
        memo=data.get('memo', ''),
        amount=to_amount,
        currency_id=data['to_currency_id'],
        cleared=data.get('cleared', False),
        approved=True,
        transfer_account_id=data['from_account_id']  # Vincula con cuenta origen
    )

    # 7. Actualizar balances
    from_account.balance += from_amount
    to_account.balance += to_amount

    # 8. Guardar todo
    db.add(from_transaction)
    db.add(to_transaction)
    db.commit()

    return [from_transaction, to_transaction]


def delete_transaction(db: Session, transaction_id: int) -> bool:
    """
    Elimina una transacción y actualiza el balance de la cuenta.

    IMPORTANTE: Si es una transferencia, también elimina la transacción vinculada.

    Args:
        db: Sesión de base de datos
        transaction_id: ID de transacción a eliminar

    Returns:
        bool: True si se eliminó exitosamente
    """
    transaction = db.query(Transaction).get(transaction_id)
    if not transaction:
        return False

    # Si es transferencia, eliminar transacción vinculada
    if transaction.transfer_account_id:
        linked = db.query(Transaction).filter(
            and_(
                Transaction.account_id == transaction.transfer_account_id,
                Transaction.transfer_account_id == transaction.account_id,
                Transaction.date == transaction.date
            )
        ).first()

        if linked:
            # Revertir balance de cuenta vinculada
            linked_account = db.query(Account).get(linked.account_id)
            if linked_account:
                linked_account.balance -= linked.amount
            db.delete(linked)

    # Revertir balance de cuenta principal
    account = db.query(Account).get(transaction.account_id)
    if account:
        account.balance -= transaction.amount

    # Eliminar transacción
    db.delete(transaction)
    db.commit()
    return True
```

---

### Capa 3: API (Endpoints) - `backend/api/`

**Propósito**: Exponer endpoints REST usando FastAPI. Solo maneja HTTP, delega lógica a servicios.

**Patrón**: Usar `APIRouter`, validación con Pydantic schemas, inyección de dependencias para DB.

#### Archivos clave:

**`backend/api/transactions.py`**
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from backend.database import get_db
from backend.services.transaction_service import create_transfer, delete_transaction

router = APIRouter()


class TransferCreate(BaseModel):
    """Schema de validación para crear transferencias"""
    from_account_id: int
    to_account_id: int
    date: date
    amount: float
    from_currency_id: int
    to_currency_id: int
    memo: Optional[str] = None
    cleared: bool = False


@router.post("/transfer")
def create_account_transfer(transfer: TransferCreate, db: Session = Depends(get_db)):
    """
    POST /api/transactions/transfer

    Crea una transferencia entre dos cuentas.

    Request body:
        {
            "from_account_id": 1,
            "to_account_id": 2,
            "date": "2025-01-14",
            "amount": 100000,
            "from_currency_id": 1,
            "to_currency_id": 2,
            "memo": "Pago de hipoteca",
            "cleared": true
        }

    Response:
        {
            "success": true,
            "from_transaction": {...},
            "to_transaction": {...}
        }
    """
    # Validaciones
    if transfer.from_account_id == transfer.to_account_id:
        raise HTTPException(400, "No se puede transferir a la misma cuenta")

    if transfer.amount <= 0:
        raise HTTPException(400, "El monto debe ser positivo")

    # Delegar a servicio
    transactions = create_transfer(db, transfer.dict())

    return {
        "success": True,
        "from_transaction": transactions[0].to_dict(),
        "to_transaction": transactions[1].to_dict()
    }


@router.delete("/{transaction_id}")
def delete_transaction_endpoint(transaction_id: int, db: Session = Depends(get_db)):
    """
    DELETE /api/transactions/{id}

    Elimina una transacción (y su vinculada si es transferencia).
    """
    success = delete_transaction(db, transaction_id)

    if not success:
        raise HTTPException(404, "Transacción no encontrada")

    return {"success": True}
```

**`backend/api/budgets.py`**
```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.services.budget_service import get_month_budget, update_budget_assignment

router = APIRouter()


@router.get("/{month}/{currency_code}")
def get_budget_for_month(month: str, currency_code: str, db: Session = Depends(get_db)):
    """
    GET /api/budgets/2025-01/COP

    Obtiene el presupuesto completo de un mes en una moneda específica.

    Response:
        {
            "ready_to_assign": 500000,
            "currency": {"id": 1, "code": "COP", "symbol": "$"},
            "groups": [
                {
                    "id": 1,
                    "name": "Gastos Esenciales",
                    "categories": [
                        {
                            "id": 1,
                            "name": "Comida",
                            "assigned": 800000,
                            "activity": -650000,
                            "available": 150000
                        }
                    ]
                }
            ]
        }
    """
    budget_data = get_month_budget(db, month + '-01', currency_code)
    return budget_data


@router.post("/assign")
def assign_budget(data: dict, db: Session = Depends(get_db)):
    """
    POST /api/budgets/assign

    Asigna presupuesto a una categoría específica.

    Request body:
        {
            "category_id": 1,
            "month": "2025-01",
            "currency_id": 1,
            "amount": 800000
        }
    """
    result = update_budget_assignment(db, data)
    return result
```

**`backend/app.py`** - Aplicación principal
```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from backend.api import (
    transactions, accounts, budgets, categories,
    exchange_rates, import_routes, mortgage,
    reports, recurring
)

# Crear aplicación
app = FastAPI(title="Personal Finance Manager", version="2.0")

# Servir archivos estáticos
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Templates
templates = Jinja2Templates(directory="frontend/templates")

# Registrar routers de API
app.include_router(transactions.router, prefix="/api/transactions", tags=["transactions"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(budgets.router, prefix="/api/budgets", tags=["budgets"])
app.include_router(categories.router, prefix="/api/categories", tags=["categories"])
app.include_router(exchange_rates.router, prefix="/api/exchange-rates", tags=["exchange-rates"])
app.include_router(import_routes.router, prefix="/api/import", tags=["import"])
app.include_router(mortgage.router, prefix="/api/mortgage", tags=["mortgage"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(recurring.router, prefix="/api/recurring", tags=["recurring"])

# Rutas HTML (renderizar templates)
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/budget")
def budget_page(request: Request):
    return templates.TemplateResponse("budget.html", {"request": request})

@app.get("/transactions")
def transactions_page(request: Request):
    return templates.TemplateResponse("transactions.html", {"request": request})

# ... más rutas HTML
```

---

## 🎨 Arquitectura Frontend

El frontend usa **plantillas HTML con JavaScript vanilla** (sin frameworks pesados).

### Estructura de una página típica:

```html
<!-- frontend/templates/accounts.html -->

<!-- Extiende el layout base -->
{% extends "layout.html" %}

{% block title %}Cuentas{% endblock %}

{% block content %}
<div class="container mx-auto px-4 py-8">
    <!-- Contenido de la página -->
    <h1>Mis Cuentas</h1>

    <div id="accountsList">
        <!-- Se llena dinámicamente con JavaScript -->
    </div>
</div>

<script>
// Variables globales
let accounts = [];
let currencies = [];
let EXCHANGE_RATE = 4000;

// Inicialización
document.addEventListener('DOMContentLoaded', async function() {
    await loadExchangeRate();
    await loadCurrencies();
    await loadAccounts();
});

// Función para cargar tasa de cambio
async function loadExchangeRate() {
    try {
        const res = await fetch('/api/exchange-rates/current');
        const data = await res.json();
        EXCHANGE_RATE = data.rate;
    } catch (error) {
        console.error('Error loading exchange rate:', error);
    }
}

// Función para cargar cuentas
async function loadAccounts() {
    try {
        const res = await fetch('/api/accounts');
        accounts = await res.json();
        displayAccounts();
    } catch (error) {
        console.error('Error loading accounts:', error);
    }
}

// Función para mostrar cuentas
function displayAccounts() {
    const container = document.getElementById('accountsList');
    container.innerHTML = accounts.map(account => `
        <div class="bg-white rounded-lg shadow p-4 mb-4">
            <h3>${account.name}</h3>
            <p>${account.currency.symbol}${formatAmount(account.balance)}</p>
        </div>
    `).join('');
}

// Helpers
function formatAmount(amount, decimals = 0) {
    return new Intl.NumberFormat('es-CO', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    }).format(Math.abs(amount));
}
</script>
{% endblock %}
```

### Patrón de comunicación:

```
Usuario interactúa
      ↓
JavaScript captura evento
      ↓
fetch() a /api/endpoint
      ↓
FastAPI endpoint (backend/api/)
      ↓
Servicio procesa (backend/services/)
      ↓
Modelo actualiza DB (backend/models/)
      ↓
Respuesta JSON
      ↓
JavaScript actualiza DOM
      ↓
Usuario ve cambio
```

---

## 🔄 Flujo de Datos Completo

### Ejemplo: Crear una transacción

```
1. Usuario llena formulario en transactions.html
   └─> Click en "Guardar"

2. JavaScript captura submit
   └─> frontend/templates/transactions.html:

       document.getElementById('transactionForm').addEventListener('submit', async (e) => {
           e.preventDefault();

           const data = {
               account_id: parseInt(document.getElementById('account').value),
               date: document.getElementById('date').value,
               payee_id: parseInt(document.getElementById('payee').value),
               category_id: parseInt(document.getElementById('category').value),
               amount: parseFloat(document.getElementById('amount').value),
               memo: document.getElementById('memo').value
           };

           const res = await fetch('/api/transactions', {
               method: 'POST',
               headers: {'Content-Type': 'application/json'},
               body: JSON.stringify(data)
           });
       });

3. Request llega a FastAPI
   └─> backend/app.py routing a transactions.router

4. Endpoint procesa
   └─> backend/api/transactions.py:

       @router.post("/")
       def create_transaction(txn: TransactionCreate, db: Session = Depends(get_db)):
           # Delega a servicio
           new_txn = create_transaction_service(db, txn.dict())
           return new_txn.to_dict()

5. Servicio ejecuta lógica
   └─> backend/services/transaction_service.py:

       def create_transaction_service(db, data):
           # Crear transacción
           transaction = Transaction(**data)
           db.add(transaction)

           # Actualizar balance de cuenta
           account = db.query(Account).get(data['account_id'])
           account.balance += data['amount']

           # Actualizar activity del presupuesto
           update_budget_activity(db, data['category_id'], data['date'], data['amount'])

           db.commit()
           return transaction

6. Modelo guarda en DB
   └─> backend/models/transaction.py (SQLAlchemy ORM)

7. Respuesta JSON vuelve a frontend
   └─> JavaScript actualiza la lista de transacciones

8. Usuario ve la transacción nueva
```

---

## 🛠️ Cómo Extender el Sistema

### Agregar un nuevo modelo

**1. Crear archivo en `backend/models/`**

```python
# backend/models/goal.py
from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base

class Goal(Base):
    """Modelo para metas de ahorro"""
    __tablename__ = 'goals'

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=False)
    target_amount = Column(Float, nullable=False)
    target_date = Column(Date)
    type = Column(String(20))  # 'target_balance', 'monthly_funding', 'target_date'

    # Relaciones
    category = relationship("Category", back_populates="goals")

    def to_dict(self):
        return {
            'id': self.id,
            'category_id': self.category_id,
            'target_amount': self.target_amount,
            'target_date': self.target_date.isoformat() if self.target_date else None,
            'type': self.type
        }
```

**2. Exportar en `backend/models/__init__.py`**

```python
from backend.models.goal import Goal

__all__ = [..., 'Goal']
```

**3. Actualizar modelo relacionado**

```python
# backend/models/category.py
class Category(Base):
    # ... campos existentes ...

    # Agregar relación
    goals = relationship("Goal", back_populates="category")
```

**4. Recrear base de datos**

```bash
rm data/finances.db
python backend/init_db.py
```

---

### Agregar un nuevo endpoint API

**1. Crear archivo en `backend/api/` o agregar a uno existente**

```python
# backend/api/goals.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from backend.database import get_db
from backend.models import Goal

router = APIRouter()


class GoalCreate(BaseModel):
    category_id: int
    target_amount: float
    target_date: Optional[date] = None
    type: str


@router.post("/")
def create_goal(goal_data: GoalCreate, db: Session = Depends(get_db)):
    """POST /api/goals - Crear meta"""
    goal = Goal(**goal_data.dict())
    db.add(goal)
    db.commit()
    return goal.to_dict()


@router.get("/category/{category_id}")
def get_category_goals(category_id: int, db: Session = Depends(get_db)):
    """GET /api/goals/category/1 - Obtener metas de categoría"""
    goals = db.query(Goal).filter_by(category_id=category_id).all()
    return [g.to_dict() for g in goals]
```

**2. Registrar router en `backend/app.py`**

```python
from backend.api import goals

app.include_router(goals.router, prefix="/api/goals", tags=["goals"])
```

---

### Agregar una nueva página

**1. Crear template en `frontend/templates/`**

```html
<!-- frontend/templates/goals.html -->
{% extends "layout.html" %}

{% block title %}Metas{% endblock %}

{% block content %}
<div class="container mx-auto px-4 py-8">
    <h1 class="text-3xl font-bold mb-6">Metas de Ahorro</h1>

    <div id="goalsList"></div>
</div>

<script>
document.addEventListener('DOMContentLoaded', async function() {
    await loadGoals();
});

async function loadGoals() {
    const res = await fetch('/api/goals');
    const goals = await res.json();
    displayGoals(goals);
}

function displayGoals(goals) {
    const container = document.getElementById('goalsList');
    container.innerHTML = goals.map(goal => `
        <div class="bg-white rounded-lg shadow p-4 mb-4">
            <h3>${goal.category.name}</h3>
            <p>Meta: $${goal.target_amount}</p>
        </div>
    `).join('');
}
</script>
{% endblock %}
```

**2. Agregar ruta en `backend/app.py`**

```python
@app.get("/goals")
def goals_page(request: Request):
    return templates.TemplateResponse("goals.html", {"request": request})
```

**3. Agregar link en navegación (`frontend/templates/layout.html`)**

```html
<nav>
    <a href="/goals">Metas</a>
</nav>
```

---

## 📊 Configuración Global

**`config.py`** - Toda la configuración centralizada

```python
# Tipos de cuenta con metadata
ACCOUNT_TYPES = {
    'checking': {
        'name': 'Cuenta Corriente',
        'icon': '💳',
        'description': 'Cuenta bancaria para uso diario',
        'can_overdraft': True,
        'tracks_interest': False
    },
    'mortgage': {
        'name': 'Hipoteca',
        'icon': '🏠',
        'description': 'Préstamo hipotecario',
        'is_debt': True,
        'interest_rate_field': True,
        'monthly_payment_field': True,
        'original_amount_field': True
    }
    # ... más tipos
}

# Configuración de APIs de tasas de cambio
EXCHANGE_RATE_API = {
    'primary': 'https://api.exchangerate-api.com/v4/latest/USD',
    'fallback': 'https://api.exchangerate.host/latest?base=USD',
    'timeout': 5,
    'retries': 2,
    'fallback_average_days': 5,
    'default_rate': 4000
}

# Configuración de base de datos
DATABASE_PATH = 'data/finances.db'
```

---

## 🐛 Debugging y Logs

### Dónde ver errores:

**Backend errors** - Terminal donde corre FastAPI:
```bash
uvicorn backend.app:app --reload
```

**Frontend errors** - Consola del navegador (F12):
```javascript
console.log('Debug:', data);
console.error('Error:', error);
```

### Herramientas útiles:

**1. FastAPI Docs automática** - http://localhost:8000/docs
   - Muestra todos los endpoints
   - Permite probarlos interactivamente

**2. SQLite Browser** - Para ver base de datos directamente
   - Descargar DB Browser for SQLite
   - Abrir `data/finances.db`

---

## 🎯 Próximas Mejoras Planificadas

Según tus requerimientos:

1. **Hipotecas con cuota fija y tasa efectiva anual**
   - Modificar `backend/services/mortgage_service.py`
   - Actualizar `backend/models/account.py` para guardar parámetros

2. **Presupuesto sin selector de moneda**
   - Modificar `frontend/templates/budget.html`
   - Permitir asignar en USD o COP directamente
   - Mostrar ambas monedas simultáneamente

3. **Categorías con acordeón**
   - Modificar `frontend/templates/budget.html`
   - Usar JavaScript para colapsar/expandir grupos

4. **Rollover behavior manual**
   - Agregar campo `rollover_behavior` a `backend/models/category.py`
   - Opciones: 'accumulate' (saving) o 'reset' (gasto mensual)

5. **Transacciones automáticas mejoradas**
   - Ya existe `backend/models/recurring_transaction.py`
   - Mejorar UI y agregar más opciones de frecuencia

---

## 📝 Convenciones de Código

### Python (Backend)

```python
# Nombres de archivos: snake_case
# budget_service.py, exchange_rate_service.py

# Nombres de clases: PascalCase
class BudgetMonth(Base):
    pass

# Nombres de funciones: snake_case
def get_month_budget(db, month_date):
    pass

# Nombres de variables: snake_case
total_assigned = 0.0
exchange_rate_usd_cop = 4000

# Docstrings: Google style
def convert_currency(amount: float, from_currency: str, to_currency: str) -> float:
    """
    Convierte una cantidad entre monedas.

    Args:
        amount: Cantidad a convertir
        from_currency: Moneda origen
        to_currency: Moneda destino

    Returns:
        float: Cantidad convertida
    """
    pass
```

### JavaScript (Frontend)

```javascript
// Nombres de variables: camelCase
let exchangeRate = 4000;
let totalAssigned = 0;

// Nombres de funciones: camelCase
async function loadAccounts() {
    // ...
}

function formatAmount(amount, decimals = 0) {
    // ...
}

// Constantes globales: SCREAMING_SNAKE_CASE
const DEFAULT_CURRENCY = 'COP';
const EXCHANGE_RATE_USD_TO_COP = 4000;

// Funciones async siempre con try/catch
async function fetchData() {
    try {
        const res = await fetch('/api/endpoint');
        const data = await res.json();
        return data;
    } catch (error) {
        console.error('Error fetching data:', error);
        alert('Error al cargar datos');
    }
}
```

---

## ✅ Checklist para Crear Nueva Funcionalidad

- [ ] **Modelo**: Crear/modificar en `backend/models/`
- [ ] **Exportar**: Agregar a `backend/models/__init__.py`
- [ ] **Migración**: Borrar DB y ejecutar `python backend/init_db.py`
- [ ] **Servicio**: Crear lógica en `backend/services/`
- [ ] **API**: Crear endpoint en `backend/api/`
- [ ] **Router**: Registrar en `backend/app.py`
- [ ] **Template**: Crear HTML en `frontend/templates/`
- [ ] **Ruta HTML**: Agregar en `backend/app.py`
- [ ] **Navegación**: Actualizar `frontend/templates/layout.html`
- [ ] **Probar**: Verificar en http://localhost:8000
- [ ] **Documentar**: Actualizar README.md si es feature mayor

---

## 🚀 Comandos Útiles

```bash
# Iniciar servidor de desarrollo
uvicorn backend.app:app --reload

# Recrear base de datos
rm data/finances.db
python backend/init_db.py

# Instalar dependencias
pip install -r requirements.txt

# Ver estructura de archivos
tree backend/

# Buscar en código
grep -r "function_name" backend/

# Ver logs de git
git log --oneline
```

---

## 💡 Recursos Adicionales

- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **SQLAlchemy Docs**: https://docs.sqlalchemy.org/
- **Tailwind CSS**: https://tailwindcss.com/docs
- **TUTORIAL.md**: Tutorial completo de uso
- **YNAB_FEATURES_COMPARISON.md**: Comparación con YNAB
- **README.md**: Documentación general del proyecto

---

Esta guía cubre la arquitectura completa del sistema. Úsala como referencia cuando quieras:
- Entender dónde está algo
- Agregar nueva funcionalidad
- Debuggear un problema
- Modificar comportamiento existente

¡Ahora tienes un mapa completo del código! 🗺️
