# System Architecture Guide

This guide explains the system's structure, how components are organized, and how they work together.

---

## Directory Structure

```
personal_finances/
├── run.py                        # App entry point
├── requirements.txt              # Python dependencies
├── data/                         # SQLite database + uploads
├── src/
│   └── finance_app/              # Main package
│       ├── app.py                # FastAPI application + route registration
│       ├── database.py           # SQLAlchemy engine and session
│       ├── config/
│       │   ├── __init__.py       # Re-exports all config constants
│       │   └── settings.py       # Centralized config (DB, currencies, alerts, account types)
│       ├── models/               # SQLAlchemy ORM models
│       ├── domain/               # Domain logic (tightly coupled to finance_app)
│       ├── api/                  # FastAPI routers (REST endpoints)
│       ├── services/             # Business logic services
│       ├── templates/            # Jinja2 HTML templates
│       ├── static/               # CSS and static assets
│       ├── sync/                 # Email scraping modules
│       └── scripts/              # CLI scripts (migrations, imports, seeds)
├── docs/                         # Project documentation
└── tests/                        # Automated tests
```

---

## Backend Architecture: 3 Layers

### Layer 1: Models — `src/finance_app/models/`

**Purpose:** Define the database schema using SQLAlchemy ORM.

**Pattern:** Each model is a class inheriting from `Base` representing a table.

**Key rule:** Always use `Numeric(18, 2)` for monetary columns. Never use `Float` — it causes rounding errors in financial calculations.

#### Key models:

**`models/account.py`** — Account model
```python
class Account(Base):
    __tablename__ = 'accounts'
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    type = Column(String(50), nullable=False)   # checking, savings, credit_card, cash, etc.
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=False)
    balance = Column(Numeric(18, 2), default=0)
    is_budget = Column(Boolean, default=True)
    is_closed = Column(Boolean, default=False)
```

**`models/transaction.py`** — Transaction model
```python
class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey('accounts.id'), nullable=False)
    date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)  # Positive=income, Negative=expense
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=False)
    transfer_account_id = Column(Integer, ForeignKey('accounts.id'))
    cleared = Column(Boolean, default=False)
```

**`models/budget.py`** — Monthly budget model
```python
class BudgetMonth(Base):
    __tablename__ = 'budget_months'
    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=False)
    month = Column(Date, nullable=False, index=True)   # First day of month
    currency_id = Column(Integer, ForeignKey('currencies.id'), nullable=False)
    assigned = Column(Numeric(18, 2), default=0)
    activity = Column(Numeric(18, 2), default=0)
    available = Column(Numeric(18, 2), default=0)
```

**`models/debt.py`** — Debt + payment models (single source of truth for all debts)
```python
class Debt(Base):
    __tablename__ = 'debts'
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    debt_type = Column(String(50))   # mortgage, credit_loan, credit_card
    principal = Column(Numeric(18, 2))
    interest_rate = Column(Numeric(10, 6))  # Stored as decimal (0.08 = 8%)
    rate_type = Column(String(20))   # effective (EA) or nominal (APR)
    monthly_payment = Column(Numeric(18, 2))
    start_date = Column(Date)
    currency_id = Column(Integer, ForeignKey('currencies.id'))

class DebtPayment(Base):
    __tablename__ = 'debt_payments'
    id = Column(Integer, primary_key=True)
    debt_id = Column(Integer, ForeignKey('debts.id'), nullable=False)
    payment_date = Column(Date, nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    principal_paid = Column(Numeric(18, 2))
    interest_paid = Column(Numeric(18, 2))
```

**`models/patrimonio_asset.py`** — Net worth assets
```python
class PatrimonioAsset(Base):
    __tablename__ = 'patrimonio_assets'
    id = Column(Integer, primary_key=True)
    nombre = Column(String(200), nullable=False)
    tipo = Column(String(50))   # inmueble, vehiculo, otro
    valor_adquisicion = Column(Numeric(18, 2))
    fecha_adquisicion = Column(Date)
    tasa_anual = Column(Numeric(10, 6))
    metodo_depreciacion = Column(String(50))   # linea_recta, saldo_decreciente, doble_saldo_decreciente
    return_rate = Column(Numeric(10, 6))   # Annual return percentage
    return_amount = Column(Numeric(18, 2)) # Fixed annual return amount
    moneda_id = Column(Integer, ForeignKey('currencies.id'))
```

---

### Layer 2: Services — `src/finance_app/services/`

**Purpose:** All business logic. Services do NOT handle HTTP, only orchestration and math.

**Sub-layers:**

**Calculators** (`services/*/calculator.py`):
- Pure functions, no DB access
- Accept model objects or dataclasses, return dicts/lists
- Easy to unit test with `SimpleNamespace` mocks

**Services** (`services/*_service.py`):
- Orchestration with DB access
- Call calculators for math
- Handle currency conversion, date logic

#### Key services:

**`services/budget_service.py`** — Budget orchestration
- `get_month_budget(db, month_date, currency_code)` — Full monthly budget with multi-currency conversion
- `calculate_ready_to_assign(db, month_date, currency_id)` — Unassigned money = accounts total - assigned total

**`services/debt/amortization_engine.py`** — Core amortization engine
- Hybrid mode: uses real `DebtPayment` records first, then projects future payments
- Supports both EA (effective annual) and APR (nominal) rates
- `calculate_balance_at_date(debt, payments, target_date)` — Balance at any point in time

**`services/patrimonio/calculator.py`** — Net worth calculator (pure functions)
- `calculate_asset_value(asset, year)` — Asset valuation with depreciation/appreciation
- `calculate_net_worth(assets, debts, year, month)` — Total net worth at a point in time
- `build_timeline(assets, debts, from_date, to_date)` — Monthly net worth timeline

**`services/transaction_service.py`** — Transaction CRUD + currency conversion
- Handles transfer creation (creates two linked transactions)
- Manages currency conversion for cross-currency transfers

**`services/exchange_rate_service.py`** — Exchange rate fetching
- Fallback chain: DB today → primary API → fallback API → 5-day average → 4000 default

---

### Layer 3: API Routers — `src/finance_app/api/`

**Purpose:** Thin HTTP layer. Validate input, call services, format response. No business logic.

**Pattern:** Each router is a FastAPI `APIRouter` mounted in `app.py`.

#### Key routers:

| File | Prefix | Responsibility |
|------|--------|---------------|
| `accounts.py` | `/api/accounts` | Account CRUD |
| `transactions.py` | `/api/transactions` | Transaction CRUD + transfers |
| `budgets.py` | `/api/budgets` | Monthly budget management |
| `debts.py` | `/api/debts` | Debt CRUD + amortization data |
| `patrimonio.py` | `/api/patrimonio` | Asset CRUD + net worth summary/timeline |
| `categories.py` | `/api/categories` | Category and group management |
| `reports_pkg/` | `/api/reports` | All report endpoints (modular) |
| `goals.py` | `/api/goals` | Financial goals |
| `exchange_rates.py` | `/api/exchange-rates` | Exchange rate retrieval |
| `import_ynab.py` | `/api/import` | Budget CSV import |

#### Report module structure (`api/reports_pkg/`):

```
reports_pkg/
├── __init__.py    # Aggregated router
├── common.py      # Shared helpers: get_exchange_rate(), parse_date_range(), convert_to_currency()
├── spending.py    # /spending-by-category, /spending-by-tag, /spending-by-group, /spending-trends
├── income.py      # /income-vs-expenses, /budget-vs-actual, /savings-rate, /summary
├── balance.py     # /balance-trend, /account-balance-history
└── debt.py        # /debt-balance-history, /debt-principal-timeline, /debt-payoff-projection
```

---

## Domain Layer — `src/finance_app/domain/`

The domain layer contains logic tightly coupled to finance_app's data model but organized for clarity:

```
domain/
├── debts/
│   ├── types.py        # Data classes (DebtPrincipalRecord)
│   ├── repository.py   # Data access (fetch_debts, fetch_snapshots)
│   ├── service.py      # Business logic (get_debts_principal)
│   ├── snapshot.py     # Snapshot building
│   └── projection.py   # Debt principal timeline projections
└── fx/
    └── service.py      # Currency conversion (to_cop, from_cop) with fallback
```

---

## Net Worth (Patrimonio) Module

The unified net worth system. All asset valuation and long-term debt tracking flows through Patrimonio.

### Design Decisions

- **No separate PatrimonioDebt model** — Patrimonio reads directly from the `Debt` model (filtering `mortgage` and `credit_loan`). This eliminates data duplication and sync issues.
- **Credit cards excluded** — Credit cards (`credit_card`) are managed only in `/debts`, not included in net worth.
- **Amortization engine** — Patrimonio calls `AmortizationEngine` directly with `Debt` objects for balance calculations.

### Asset Valuation Formula

```
value = valor_adquisicion * (1 + tasa_anual) ^ max(0, year - acquisition_year - 1)
```

- Acquisition year → original value
- Before acquisition year → 0
- Each subsequent year → compounded growth/depreciation

### API Endpoints

```
GET  /api/patrimonio/resumen?año=&mes=          # Net worth summary (assets + debts)
GET  /api/patrimonio/timeline?desde=&hasta=     # Monthly timeline
GET  /api/patrimonio/activos                    # List all assets
POST /api/patrimonio/activos                    # Create asset
PUT  /api/patrimonio/activos/{id}               # Update asset
DELETE /api/patrimonio/activos/{id}             # Delete asset
GET  /api/patrimonio/activos/{id}/timeline      # Asset value timeline
GET  /api/patrimonio/deudas/{id}/amortizacion   # Read-only debt amortization
```

---

## Currency System

- **Base currency**: COP (id=1)
- **Secondary**: USD (id=2)
- Exchange rates stored in `exchange_rates` table (daily records)
- `domain/fx/service.py` provides `to_cop()` and `from_cop()` with fallback
- All monetary API responses include a `currency` dict:
  ```json
  { "id": 1, "code": "COP", "symbol": "₱", "exchange_rate_to_base": 1.0 }
  ```

---

## Interest Rate Conventions

| Convention | Formula | When to use |
|-----------|---------|-------------|
| Effective annual (EA) | `monthly = (1 + annual)^(1/12) - 1` | Colombian debts (default) |
| Nominal APR | `monthly = annual / 12` | US-style debts |

Document the convention in `debt.notes`. Default is `effective`.

---

## Testing Strategy

```
tests/
├── test_patrimonio_calculator.py   # Pure calculator tests (no DB)
├── test_budget_service.py          # Service tests with in-memory SQLite
└── ...
```

**Principles:**
- Calculator tests use `SimpleNamespace` or dataclasses to mock models — no DB needed
- Service/API tests use in-memory SQLite with `get_db` dependency override
- Use hardcoded expected values with explicit tolerances for financial math
- Name files `tests/test_<module>.py`

**Run tests:**
```bash
python -m pytest tests/ -v
python -m pytest tests/test_patrimonio_calculator.py -v
```

---

## Adding a New Financial Module

1. Create SQLAlchemy model in `models/` — use `Numeric(18,2)` for all money fields
2. Write calculator in `services/<module>/calculator.py` — pure functions first
3. Write tests against the calculator with known expected values
4. Build API router in `api/<module>.py`, register in `app.py`
5. Create Jinja2 template in `templates/<module>/`, add sidebar link in `base.html`
6. Add migration script to `scripts/migrate_db.py` if needed
