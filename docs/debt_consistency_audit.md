# Debt Consistency Audit

## Endpoints / Routes that compute debt or net worth

- **`GET /api/debts/`** (`src/finance_app/api/debts.py`)
  - Debt list with balances; mortgages recalc using `calculate_debt_balance_as_of`.
- **`GET /api/debts/summary`** (`src/finance_app/api/debts.py`)
  - Totals by type/currency; uses current balances and mortgage recalculation.
- **`GET /api/reports/debt-balance-history`** (`src/finance_app/api/reports.py`)
  - Monthly debt totals; uses `_calculate_debt_balance` (interest + payments) and currency conversion.
- **`GET /api/reports/debt-principal-timeline`** (`src/finance_app/api/reports.py`)
  - Monthly debt principal timeline; uses inferred payments + interest accrual.
- **`GET /api/reports/debt-summary`** (`src/finance_app/api/reports.py`)
  - Summary of active debts; computes current/projected balances via `_calculate_debt_balance`.
- **`GET /api/reports/net-worth`** (`src/finance_app/api/reports.py`)
  - Net worth history; liabilities computed via `_calculate_debt_balance` and currency conversion.
- **`GET /debts`** page (`src/finance_app/app.py` + `templates/debts.html`)
  - Fetches `/api/debts` and `/api/debts/summary` for UI totals.
- **`GET /reports`** page (`src/finance_app/templates/reports.html`)
  - Calls `/api/reports/debt-summary` for totals.
- **`GET /wealth`** page (`src/finance_app/templates/wealth.html`)
  - Uses `/api/reports/net-worth` and debt endpoints indirectly.

## Functions/services computing debt totals or balances

- **`_debt_to_dict_with_calculated_balance`** (`src/finance_app/api/debts.py`)
  - Mortgage balance computed with `calculate_debt_balance_as_of`; others use stored `current_balance`.
- **`calculate_debt_balance_as_of`** (`src/finance_app/services/debt_balance_service.py`)
  - Recalculates balance with interest + principal payments; optional projection.
- **`build_debt_principal_timeline`** (`src/finance_app/api/reports.py`)
  - Builds month-by-month principal using interest + inferred payments.
- **`_calculate_debt_balance`** (`src/finance_app/api/reports.py`)
  - Wrapper around `calculate_debt_balance_as_of`.

## Currency conversion logic

- **`convert_to_currency`** (`src/finance_app/api/reports.py`)
  - Converts between COP/USD using `exchange_rate` param.
- **`get_exchange_rate`** (`src/finance_app/api/reports.py`)
  - Pulls latest `ExchangeRate`; fallback 4000 COP/USD.
- **`Currency.exchange_rate_to_base`** (`src/finance_app/models/currency.py`)
  - Currency table stores rate to base (COP).
- **`currency_service.convert_to_base` / `convert_currency`** (`src/finance_app/services/currency_service.py`)
  - Converts using `exchange_rate_to_base`.

## Scheduled payments logic

- **`RecurringTransaction` model** (`src/finance_app/models/recurring_transaction.py`)
  - Represents scheduled (recurring) payments by category.
- **`recurring_service.get_next_scheduled_date` / `generate_due_transactions`** (`src/finance_app/services/recurring_service.py`)
  - Calculates next schedule and generates transactions.

## Computation path classification

- **Canonical candidate (Gestion/Deudas)**
  - `GET /api/debts` + `_debt_to_dict_with_calculated_balance` in `debts.py`.
    - Uses stored `current_balance` for credit cards/loans and mortgage recalculation for mortgages.

- **Duplicate paths**
  - `reports.get_debt_summary`: recomputes balances via `_calculate_debt_balance`.
  - `reports.get_debt_balance_history`: recomputes balances via `_calculate_debt_balance`.
  - `reports.get_net_worth`: recomputes balances via `_calculate_debt_balance`.
  - `reports.build_debt_principal_timeline`: separate projection logic.

- **Inconsistent paths**
  - `calculate_debt_balance_as_of` includes interest accrual and principal payments for loans/mortgages,
    while Gestion/Deudas treats non-mortgage balances as stored `current_balance` only.
  - `reports` endpoints use interest-bearing recomputation and may return totals that differ from
    Gestion/Deudas (principal-only) rules.

