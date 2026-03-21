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
├── models/                 # SQLAlchemy ORM models
├── api/                    # FastAPI routers (REST endpoints)
│   ├── reports/            # Report endpoints (modular)
│   │   ├── __init__.py     # Aggregated router
│   │   ├── common.py       # Shared helpers (currency, dates, queries)
│   │   ├── spending.py     # Spending by category/tag/group
│   │   ├── income.py       # Income vs expenses, budget comparisons
│   │   ├── balance.py      # Balance trends, account history
│   │   ├── debt.py         # Debt balance, principal timeline, payoff
│   │   └── wealth.py       # Net worth, real estate wealth
│   └── ...                 # Other API modules
├── services/               # Business logic services
│   └── reports/            # Report-specific service layer
│       ├── __init__.py
│       └── debt_timeline.py # Debt principal timeline builder
├── templates/
│   ├── base.html           # Layout with sidebar navigation
│   ├── reports/            # Report page templates
│   │   ├── index.html      # Main reports dashboard
│   │   ├── budget.html     # Budget vs expenses report
│   │   ├── wealth.html     # Real estate wealth report
│   │   └── investments.html # Investments report
│   └── ...                 # Other page templates
├── static/styles/          # CSS (design-system.css)
├── utils/                  # Utility functions (wealth calculations)
├── sync/                   # Email/Telegram sync modules
├── scripts/                # CLI scripts (migrations, imports)
└── config/                 # App settings
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
- **Import style**: Relative imports within `finance_app` package, absolute for `domain`.

## Report System (api/reports/)

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
