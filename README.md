# Personal Finances

A Personal finance manager built with FastAPI + SQLAlchemy + Jinja2. Multi-currency (COP/USD), budgeting, debt tracking, net worth (Patrimonio), and investment simulation.

---

## Features

- **Budgeting**: Categories with rollover (accumulate vs reset), Ready to Assign, multi-currency assignments
- **Multi-currency**: COP and USD with automatic conversion, rates from external API with fallback, per-transaction FX audit
- **Net Worth (Patrimonio)**: Assets (real estate, vehicles, other) with depreciation and returns. Debts integrated directly from the debts module. Net worth timeline
- **Debts**: Mortgages, personal loans, credit cards. Hybrid amortization engine (real payments + projections). Principal balance timeline
- **Financial Goals**: Visual tracking of savings objectives
- **Emergency Fund**: Calculation and tracking
- **Reports**: Spending by category/tag/group, income vs expenses, balance trends, financial health
- **Investment Simulator**: Compound interest projections
- **CSV Importer**: CSV import with category detection, transfer handling, and deduplication
- **Recurring Transactions**: Automation of regular payments
- **Gmail Integration**: Scraping transactions from bank notification emails
- ~~**Telegram Integration**~~ *(deprecated)*

---

## Quick Start

### Requirements

- Python 3.10+

### Installation

```bash
git clone https://github.com/oscarems/personal_finances.git
cd personal_finances
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

### Initialize Database

```bash
python src/finance_app/scripts/init_db.py
```

Creates SQLite at `data/finances.db` with pre-seeded currencies, categories, and groups.

### Run

```bash
python run.py
```

- App: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Demo Mode

```bash
DEMO_MODE=true python run.py
```

Uses `data/finances_demo.db` without touching your real database. You can also switch databases from the sidebar selector.

### External Database

```bash
DATABASE_URL="postgresql+psycopg2://user:pass@localhost:5432/finanzas" python run.py
```

---

## Architecture

```
src/finance_app/
├── app.py                    # FastAPI app + route registration
├── database.py               # SQLAlchemy engine, sessions
├── config/settings.py        # Centralized configuration
├── models/                   # ORM models
│   ├── patrimonio_asset.py   # Assets with depreciation/returns
│   ├── debt.py               # Debts + payments
│   └── debt_amortization.py  # Monthly amortization records
├── domain/                   # Domain logic
│   ├── debts/                # Projections, snapshots, repository
│   └── fx/                   # Currency conversion
├── api/                      # FastAPI routers
│   ├── patrimonio.py         # Asset CRUD + summary/timeline
│   ├── debts.py              # Debt CRUD + amortization
│   ├── budgets.py            # Monthly budgeting
│   ├── reports_pkg/          # Modular reports (spending, income, balance, debt)
│   └── ...                   # accounts, goals, transactions, etc.
├── services/                 # Business logic
│   ├── debt/                 # Amortization, balance, timeline
│   ├── patrimonio/           # Asset valuation, net worth
│   ├── mortgage/             # Mortgage calculations
│   └── ...                   # budget, transaction, alert, etc.
├── templates/                # Jinja2 + Tailwind CSS
└── scripts/                  # Migration, import, seed scripts
```

### Code Conventions

| Aspect | Convention |
|--------|-----------|
| Money columns | `Numeric(18, 2)` — never `Float` |
| Dates | `datetime.date`, `Date` columns |
| Interest rates | Decimals (0.08 = 8%), annual by default |
| Transactions | Negative = expense, positive = income |
| Imports | Absolute: `from finance_app.xxx import ...` |
| Config | `from finance_app.config import ...` |
| UI | Spanish language, Tailwind utility classes |
| API responses | Always include `currency` dict for monetary values |

### Layers

- **Calculators** (`services/*/calculator.py`): Pure functions, no DB access. Accept objects, return data.
- **Services** (`services/*_service.py`): Orchestration with DB access. Call calculators for math.
- **API routers** (`api/*.py`): Thin HTTP layer. Validate input, call services, format response. No business logic.

### Interest Rate Conventions

- **Colombia (EA)**: Effective annual rate → `monthly = (1 + annual)^(1/12) - 1`
- **US (APR)**: Nominal rate → `monthly = annual / 12`
- Default: `effective`. Document convention in `debt.notes`.

---

## Core Modules

### Budget

- **Ready to Assign** = Total in accounts - Total assigned
- **Rollover Reset**: Unspent money returns to Ready to Assign next month (for monthly expenses)
- **Rollover Accumulate**: Unspent money carries forward (for savings and goals)
- Assignments in COP or USD, summed and converted to the display currency

### Net Worth (Patrimonio)

Unified net worth system:
- **Assets**: `inmueble`, `vehiculo`, `otro` with depreciation methods (straight-line, declining balance, double declining)
- **Debts**: Reads directly from the `Debt` model (mortgages + personal loans). No data duplication.
- **Valuation**: Annual from acquisition date with configurable return rate
- **Timeline**: 24 months past + 24 months future

### Debts

- Types: `mortgage`, `credit_loan`, `credit_card`
- Hybrid amortization engine: real recorded payments + future projections
- Principal balance timeline with projections
- Credit cards appear only in `/debts`, not in net worth

### Reports

Module `api/reports_pkg/` split into focused files:
- `spending.py` — Spending by category, tag, group, trends
- `income.py` — Income vs expenses, budget vs actual, savings rate
- `balance.py` — Balance trend, account history
- `debt.py` — Debt history, principal timeline, payoff projection

---

## REST API

Interactive documentation at http://localhost:8000/docs

```
GET/POST            /api/accounts/                 # Accounts
GET/POST            /api/transactions/             # Transactions
POST                /api/transactions/transfer     # Transfers
GET/POST            /api/budgets/                  # Budget
GET/POST/PUT        /api/debts/                    # Debts
GET/POST/PUT/DELETE /api/patrimonio/activos/       # Net worth assets
GET                 /api/patrimonio/resumen        # Net worth summary
GET                 /api/patrimonio/timeline       # Net worth timeline
GET                 /api/reports/                  # Reports
GET                 /api/exchange-rates/           # Exchange rates
POST                /api/import/csv              # Import budget CSV
GET/POST            /api/goals/                    # Financial goals
```

---

## Testing

```bash
# All tests
python -m pytest tests/ -v

# Specific test
python -m pytest tests/test_patrimonio_calculator.py -v
```

- Calculator tests use hardcoded expected values with explicit tolerances for floating-point math
- Use `SimpleNamespace` or dataclasses to mock models (avoid DB when possible)
- API tests use in-memory SQLite with `get_db` override

---

## Optional Configuration

### Gmail Integration

Allows the app to read bank notification emails and import them as transactions automatically. Requires a Gmail account with secure access configured.

#### Setup Steps

**1. Enable IMAP in Gmail**
1. Open Gmail → Settings (gear icon) → See all settings
2. Go to the **"Forwarding and POP/IMAP"** tab
3. Under IMAP, select **"Enable IMAP"**
4. Save changes

**2. Enable Two-Step Verification**
1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Under "How you sign in to Google", enable **"2-Step Verification"**
3. Follow the setup wizard

**3. Generate an App Password**
1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Choose application **"Mail"**
3. Choose device **"Other (custom name)"** → type `finances`
4. Click **Generate**
5. Copy the 16-character password (format: `xxxx xxxx xxxx xxxx`)

**4. Configure in .env**

```bash
GMAIL_EMAIL="yourmail@gmail.com"
GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
```

> Use the generated App Password, **not** your regular Gmail password.
> The App Password has spaces — copy it exactly as shown.

**Supported bank emails:**
- Bancolombia (Colombia)
- BAC / Panamá banks
- Mastercard Black

Once configured, go to **Advanced → Import Gmail** in the app to review and register detected emails.

### Exchange Rates

Fallback order: today's rate in DB → primary API → fallback API → 5-day average → default (4000 COP/USD).

---

## Tech Stack

- **Backend**: FastAPI + Uvicorn + SQLAlchemy (SQLite)
- **Frontend**: Jinja2 + Tailwind CSS (CDN) + Chart.js + Vanilla JS
- **Testing**: pytest

---

## License

Personal use project.
