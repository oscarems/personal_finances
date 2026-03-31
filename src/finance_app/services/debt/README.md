# Debt Amortization Module

## Purpose

Generates month-by-month amortization schedules for mortgages and credit loans.
Schedules can be purely theoretical (plan), based on recorded payments (actual),
or a mix of both (hybrid). The module also persists schedule rows to the
`debt_amortization_monthly` table for use by reports and projections.

## Architecture

The module is split into three layers:

```
AmortizationEngine          Pure calculation logic. No writes to DB.
  (amortization_engine.py)  Generates schedules, computes balances.
        │
        ▼
amortization_service.py     Orchestration layer. Iterates active debts,
                            calls the engine, and upserts rows into
                            DebtAmortizationMonthly. Also provides
                            query helpers (fetch by month / range).
        │
        ▼
DebtAmortizationMonthly     SQLAlchemy model. One row per debt per month.
  (models/debt_amortization.py)
```

**AmortizationEngine** (`amortization_engine.py`)
- Stateless calculator instantiated with an optional `Session` (needed only to
  read real payments) and a rate convention.
- Key methods: `generate_schedule(debt, as_of, mode)` and
  `balance_as_of(debt, date, mode)`.
- Returns plain dicts (via `ScheduleEntry.to_dict()`).

**amortization_service.py**
- `ensure_debt_amortization_records(db, start, end)` -- bulk-generate/update
  persisted records for all active debts. Called on app startup and by reports.
- `fetch_amortization_for_month(db, month)` / `fetch_amortization_range(db, start, end)` --
  read helpers that return `{debt_id: record}` or `{(debt_id, date): record}`.

**DebtAmortizationMonthly** (`models/debt_amortization.py`)
- Columns: `principal_payment`, `interest_payment`, `total_payment`,
  `principal_remaining`, `interest_rate_calculated`, `status`.
- Unique constraint on `(debt_id, as_of_date)`.
- `status` is either `"pagado"` (derived from real payments) or `"proyeccion"`.

## Amortization Types

Detected automatically from `debt.notes` (case-insensitive keyword match),
falling back to `debt.debt_type`:

| Type | Trigger keywords in `debt.notes` | Fallback |
|---|---|---|
| **fixed_payment** (French) | `cuota_fija`, `fixed_payment`, `frances`, `francés` | Default for `mortgage` and `credit_loan` |
| **fixed_principal** (German) | `capital_fijo`, `fixed_principal`, `aleman`, `alemán` | -- |
| **interest_only** | `solo_interes`, `interest_only`, `sólo interés`, `solo interes` | -- |

`credit_card` debts are skipped entirely.
If no keyword matches and the debt type is not mortgage/credit_loan, an
`UnsupportedAmortizationTypeError` is raised.

## Schedule Modes

Pass `mode` to `generate_schedule()`:

| Mode | Behavior |
|---|---|
| `plan` | Entire schedule is theoretical. Real payments are ignored. |
| `actual` | Uses recorded `DebtPayment` / `MortgagePaymentAllocation` rows. Stops after `as_of`. |
| `hybrid` | Real payments for past months, planned payments for future months. **This is the default for most callers.** |

Real payments are collected from three sources (in priority order):
1. `MortgagePaymentAllocation` records
2. `DebtPayment` records (excluding those already covered by allocations)
3. Heuristic transaction matching by category + account + memo keywords

## Interest Rate Conventions

Set via `annual_rate_convention` on the engine constructor:

| Convention | Formula | When to use |
|---|---|---|
| `effective` (default) | `monthly = (1 + annual)^(1/12) - 1` | Colombian mortgage rates (EA) |
| `nominal` | `monthly = annual / 12` | US-style APR |

Additionally, if `debt.notes` contains `tasa_mensual` or `monthly_rate`, the
stored rate is treated as already-monthly (no conversion).

## Usage Example

```python
from finance_app.services.debt.amortization_engine import AmortizationEngine
from finance_app.services.debt.amortization_service import ensure_debt_amortization_records

# --- Generate a schedule in-memory (no persistence) ---
engine = AmortizationEngine(db=session, annual_rate_convention="effective")
schedule = engine.generate_schedule(debt, as_of=date(2026, 12, 1), mode="hybrid")
for row in schedule:
    print(row["date"], row["opening_balance"], row["principal"], row["ending_balance"])

# Get balance at a specific date
balance = engine.balance_as_of(debt, date(2026, 6, 1))

# --- Persist schedule rows for all active debts ---
ensure_debt_amortization_records(db=session, start_month=date(2026, 1, 1), end_month=date(2026, 12, 1))
```

## Running Tests

```bash
# All amortization tests
python -m pytest tests/test_amortization_engine.py tests/test_amortization_fixes.py -v

# Full test suite
python -m pytest tests/ -v
```
