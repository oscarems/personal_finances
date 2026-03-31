# Personal Finances - Claude Code Guide

## Project Overview
YNAB-style personal finance manager built with FastAPI + SQLAlchemy + Jinja2 templates.
Supports multi-currency (COP/USD), budgeting, debt tracking, net worth (Patrimonio),
and investment simulation.

## Architecture

```
src/finance_app/
├── app.py                  # FastAPI app, route registration, startup
├── database.py             # SQLAlchemy engine, session, init
├── init_db.py              # Database initialization with seed data
├── config/
│   ├── __init__.py         # Re-exports all config constants
│   └── settings.py         # All configuration (DB, currencies, alerts, account types, env settings)
├── models/                 # SQLAlchemy ORM models
│   ├── patrimonio_asset.py # PatrimonioAsset model (inmueble, vehiculo, otro) with depreciation + return fields
│   ├── debt.py             # Debt + DebtPayment models (single source of truth for all debts)
│   └── debt_amortization.py # DebtAmortizationMonthly (Numeric(18,2) columns)
├── domain/                 # Domain logic (tightly coupled to finance_app)
│   ├── debts/              # Debt projections, snapshots, repository
│   │   ├── types.py        # Data classes (DebtPrincipalRecord)
│   │   ├── repository.py   # Data access (fetch_debts, fetch_snapshots)
│   │   ├── service.py      # Business logic (get_debts_principal)
│   │   ├── snapshot.py     # Snapshot building
│   │   └── projection.py   # Debt principal timeline projections
│   └── fx/
│       └── service.py      # Currency conversion (to_cop, from_cop) with fallback
├── api/                    # FastAPI routers (REST endpoints)
│   ├── patrimonio.py       # Patrimonio CRUD + resumen/timeline endpoints
│   ├── reports_pkg/        # Report endpoints (modular)
│   │   ├── __init__.py     # Aggregated router
│   │   ├── common.py       # Shared helpers (currency, dates, queries)
│   │   ├── spending.py     # Spending by category/tag/group
│   │   ├── income.py       # Income vs expenses, budget comparisons
│   │   ├── balance.py      # Balance trends, account history
│   │   └── debt.py         # Debt balance, principal timeline, payoff
│   └── ...                 # Other API modules (accounts, budgets, debts, etc.)
├── services/               # Business logic services
│   ├── debt/               # Debt-related services (see services/debt/README.md)
│   │   ├── amortization_engine.py  # Core amortization calculation engine
│   │   ├── amortization_service.py # Amortization record management
│   │   ├── balance_service.py      # Debt balance calculations
│   │   ├── helpers.py              # Debt payment helpers (extracted from api/debts.py)
│   │   ├── timeline.py            # Debt principal timeline builder
│   │   └── README.md              # Module documentation
│   ├── patrimonio/         # Patrimonio (unified net worth) services
│   │   ├── calculator.py          # Asset valuation, debt balance via AmortizationEngine, net worth timeline
│   │   └── __init__.py
│   ├── mortgage/           # Mortgage-related services
│   │   ├── service.py              # Mortgage calculations
│   │   └── allocation_service.py   # Payment allocation logic
│   ├── transaction_service.py      # Transaction CRUD + currency conversion
│   ├── transaction_allocation_service.py
│   ├── budget_service.py
│   ├── exchange_rate_service.py    # External API rate fetching
│   ├── alert_service.py
│   ├── emergency_fund_service.py
│   ├── goal_service.py
│   ├── investment_simulator_service.py
│   ├── microsoft_graph_service.py
│   ├── reconciliation_service.py
│   └── recurring_service.py
├── templates/
│   ├── base.html           # Layout with sidebar navigation
│   ├── patrimonio/         # Patrimonio pages (dashboard, activos, deudas)
│   ├── reports/            # Report page templates
│   └── ...                 # Other page templates
├── static/styles/          # CSS (design-system.css)
├── sync/                   # Email sync modules
│   ├── email_scrape.py     # CLI wrapper
│   └── email_scrape_sync.py # Email scraping implementation
├── scripts/                # CLI scripts (migrations, imports)
│   ├── init_db.py          # DB initialization wrapper
│   ├── import_ynab.py      # YNAB CSV import
│   ├── generate_recurring.py
│   ├── migrate_db.py
│   ├── seed_categories.py
│   ├── reset_database.py
│   ├── recalculate_savings_budgets.py
│   └── test_csv_reader.py
└── utils/
    └── ynab_importer.py    # YNAB CSV parsing utility
```

## Tech Stack
- **Backend**: FastAPI + Uvicorn
- **ORM**: SQLAlchemy (SQLite)
- **Templates**: Jinja2 + Tailwind CSS (CDN)
- **Charts**: Chart.js
- **Language**: Python 3.x, HTML/JS frontend

## Key Commands

```bash
# Run the app
python run.py
# or
uvicorn finance_app.app:app --reload --host 0.0.0.0 --port 8000

# Run tests
python -m pytest tests/ -v

# Run a specific test
python -m pytest tests/test_patrimonio_calculator.py -v
```

## Key Conventions

- **Currency**: COP (id=1) is base currency, USD (id=2). Exchange rate stored in `exchange_rates` table.
- **Dates**: All date ranges default to current month. Minimum supported: January 2026.
- **Transactions**: Negative = expense, Positive = income. Transfers use `transfer_account_id`.
- **Debt types**: `mortgage`, `credit_loan`, `credit_card`.
- **Patrimonio types**: Assets are `inmueble`, `vehiculo`, `otro`. Debts are `hipoteca`, `consumo` (no `tarjeta` — credit cards are managed in `/debts`).
- **Templates**: Extend `base.html`. Spanish language UI. Use Tailwind utility classes.
- **API responses**: Always include `currency` dict when returning monetary values.
- **Import style**: Use `from finance_app.xxx import ...` (absolute within the package). Config imports use `from finance_app.config import ...`.
- **Monetary columns**: Always use `Numeric(precision=18, scale=2)` for money. Never use `Float` — it causes rounding errors.
- **Patrimonio reads Debt directly**: Patrimonio uses the `Debt` model (not a separate table) for net worth calculations. The `AmortizationEngine` is called directly with `Debt` objects.

## Best Practices

### Data Types
- **Money**: `Numeric(18, 2)` in SQLAlchemy models. Never `Float`.
- **Dates**: Use `datetime.date` objects. Store as `Date` columns, not strings.
- **Rates**: Store as decimals (0.08 = 8%). Annual unless `debt.notes` says otherwise.

### Module Structure
- **Calculators** (`services/*/calculator.py`): Pure functions, no DB access. Take model objects or dataclasses as input, return dicts/lists. Easy to test.
- **Services** (`services/*_service.py`): Orchestration layer with DB access. Call calculators for math.
- **API routers** (`api/*.py`): Thin HTTP layer. Validate input, call services, format response. No business logic.

### Adding New Financial Modules
1. Create SQLAlchemy model in `models/` with `Numeric(18,2)` for money fields.
2. Write calculator in `services/<module>/calculator.py` — pure functions first.
3. Write tests against the calculator with known expected values.
4. Build API router in `api/<module>.py`, register in `app.py`.
5. Create Jinja2 template in `templates/<module>/`, add sidebar link in `base.html`.

### Testing
- Test calculators with hardcoded expected values and explicit tolerances for floating-point math.
- Use `SimpleNamespace` or dataclasses to mock model objects in calculator tests — avoid DB when possible.
- For API tests, use in-memory SQLite with `get_db` override.
- Name test files `tests/test_<module>.py`. Group related tests in classes.

### Interest Rate Conventions
- Colombian rates are typically **effective annual (EA)**: `monthly = (1 + annual)^(1/12) - 1`
- US-style rates are **nominal (APR)**: `monthly = annual / 12`
- Default to `effective` unless specified. Document convention in `debt.notes`.

### Currency
- All monetary API responses include a `currency` dict.
- COP is base (id=1). USD (id=2) converts via `exchange_rates` table.
- Patrimonio module stores `moneda_id` per asset/debt for multi-currency support.

## Patrimonio Module

The **single unified net worth system**. All asset valuation and long-term debt tracking flows through Patrimonio (the legacy `services/wealth/` system has been consolidated here).

### Asset Valuation
- Valuation on January 1st each year, constant through Dec.
- Formula: `value = valor_adquisicion * (1 + tasa_anual) ^ max(0, year - year_acquisition - 1)`
- Acquisition year returns original value. Before acquisition returns 0.
- **Depreciation methods** (`metodo_depreciacion`): `linea_recta`, `saldo_decreciente`, `doble_saldo_decreciente`.
- **Return fields**: `return_rate` (percentage) and `return_amount` (fixed annual) for investment-type assets.

### Debts in Patrimonio
- **Single source of truth**: Debts are managed in `/debts` (Debt model). Patrimonio reads directly from the `debts` table, filtering mortgage + credit_loan (excludes credit cards).
- **No separate PatrimonioDebt model** — eliminated to avoid data duplication and sync issues.
- Patrimonio uses the `AmortizationEngine` in hybrid mode (real payments + projected) for balance calculations.
- **No credit cards in patrimonio**: Tarjetas de credito are managed only in `/debts`.

### API Endpoints (`/api/patrimonio/`)
- `GET /resumen?año=&mes=` — Summary with assets, debts, net worth
- `GET /timeline?desde=YYYY-MM&hasta=YYYY-MM` — Monthly timeline
- CRUD: `/activos` (assets only — debts managed via `/api/debts`)
- `GET /activos/{id}/timeline`, `GET /deudas/{id}/amortizacion` (read-only for debts)

### Frontend Pages
- `/patrimonio` — Dashboard with summary cards + Chart.js timeline (24mo past + 24mo future)
- `/patrimonio/activos` — Asset list with valuations, timeline chart, add/edit forms
- `/patrimonio/deudas` — Read-only debt view with progress bars and amortization table (edit in `/debts`)

## Report System (api/reports_pkg/)

The report module is split into focused files:
- `common.py` — Shared utilities: `get_exchange_rate()`, `parse_date_range()`, `convert_to_currency()`, expense allocation helpers
- `spending.py` — `/spending-by-category`, `/spending-by-tag`, `/spending-by-group`, `/spending-trends`
- `income.py` — `/income-vs-expenses`, `/budget-income-expenses`, `/top-income-expenses`, `/budget-vs-actual`, `/savings-rate`, `/summary`, `/period-summary`
- `balance.py` — `/balance-trend`, `/account-balance-history`
- `debt.py` — `/debt-balance-history`, `/debt-principal-timeline`, `/debt-summary`, `/debt-payoff-projection`

## Testing
- Tests live in `tests/` directory
- Use in-memory SQLite for test isolation
- Import API functions directly for unit testing (e.g., `from finance_app.api.patrimonio import ...`)
- Calculator/service tests should use plain objects or dataclasses, not DB sessions when possible
