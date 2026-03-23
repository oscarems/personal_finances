# Personal Finances - Claude Code Guide

## Project Overview
YNAB-style personal finance manager built with FastAPI + SQLAlchemy + Jinja2 templates.
Supports multi-currency (COP/USD), budgeting, debt tracking, wealth/net worth analysis,
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
│   ├── reports_pkg/        # Report endpoints (modular)
│   │   ├── __init__.py     # Aggregated router
│   │   ├── common.py       # Shared helpers (currency, dates, queries)
│   │   ├── spending.py     # Spending by category/tag/group
│   │   ├── income.py       # Income vs expenses, budget comparisons
│   │   ├── balance.py      # Balance trends, account history
│   │   ├── debt.py         # Debt balance, principal timeline, payoff
│   │   └── wealth.py       # Net worth, real estate wealth
│   └── ...                 # Other API modules (accounts, budgets, debts, etc.)
├── services/               # Business logic services
│   ├── debt/               # Debt-related services
│   │   ├── amortization_engine.py  # Core amortization calculation engine
│   │   ├── amortization_service.py # Amortization record management
│   │   ├── balance_service.py      # Debt balance calculations
│   │   ├── helpers.py              # Debt payment helpers (extracted from api/debts.py)
│   │   └── timeline.py            # Debt principal timeline builder
│   ├── mortgage/           # Mortgage-related services
│   │   ├── service.py              # Mortgage calculations
│   │   └── allocation_service.py   # Payment allocation logic
│   ├── wealth/             # Wealth & net worth services
│   │   ├── net_worth_service.py    # Net worth orchestrator
│   │   ├── real_estate_service.py  # Real estate wealth timeline
│   │   └── helpers.py              # Asset appreciation/depreciation functions
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
python -m pytest tests/test_reports_wealth.py -v
```

## Key Conventions

- **Currency**: COP (id=1) is base currency, USD (id=2). Exchange rate stored in `exchange_rates` table.
- **Dates**: All date ranges default to current month. Minimum supported: January 2026.
- **Transactions**: Negative = expense, Positive = income. Transfers use `transfer_account_id`.
- **Wealth assets**: Classes are `inmueble`, `activo`, `inversion`. Category mapping: inmueble/activo → "bienes", inversion → "inversiones".
- **Debt types**: `mortgage`, `credit_loan`, `credit_card`.
- **Templates**: Extend `base.html`. Spanish language UI. Use Tailwind utility classes.
- **API responses**: Always include `currency` dict when returning monetary values.
- **Import style**: Use `from finance_app.xxx import ...` (absolute within the package). Config imports use `from finance_app.config import ...`.

## Report System (api/reports_pkg/)

The report module is split into focused files:
- `common.py` — Shared utilities: `get_exchange_rate()`, `parse_date_range()`, `convert_to_currency()`, expense allocation helpers
- `spending.py` — `/spending-by-category`, `/spending-by-tag`, `/spending-by-group`, `/spending-trends`
- `income.py` — `/income-vs-expenses`, `/budget-income-expenses`, `/top-income-expenses`, `/budget-vs-actual`, `/savings-rate`, `/summary`, `/period-summary`
- `balance.py` — `/balance-trend`, `/account-balance-history`
- `debt.py` — `/debt-balance-history`, `/debt-principal-timeline`, `/debt-summary`, `/debt-payoff-projection`
- `wealth.py` — `/net-worth`, `/real-estate-wealth`

## Testing
- Tests live in `tests/` directory
- Use in-memory SQLite for test isolation
- Import API functions directly for unit testing (e.g., `from finance_app.api.reports_pkg.wealth import get_net_worth`)
