# Debt Principal Definition

## Definition: Debt principal (capital)
- **Debt principal** is the unpaid capital balance of a debt.
- **Interest, fees, and penalties are excluded** from all totals and projections.
- The **canonical source of truth** for principal is the **Gestion/Deudas** computation
  (stored current balance for credit cards/loans; mortgage balance calculated from payments).

## Currency conversion to COP
- All reporting totals are in **COP**.
- Conversion uses, in order:
  1) **`ExchangeRate` table** (latest rate on or before the as-of date),
  2) **`Currency.exchange_rate_to_base`** when present,
  3) **`DEFAULT_EXCHANGE_RATES`** in `config.py` as a fallback.
- All conversions return **Decimal** values and are quantized to **2 decimals** for consistent reporting.

## Snapshot timing rule
- Monthly snapshots are taken on the **first day of each month** (e.g., `2026-02-01`).
- Each snapshot row stores the principal in original currency and COP for that first day.

## Projection rule (scheduled payments)
- Future projections use **scheduled payments (pagos programados)** from `RecurringTransaction`.
- For each month `M`, payments in `[M, next_month)` reduce principal.
- **Payment-to-debt allocation (category-based):**
  1) If a **debt/category mapping** exists, use it.
  2) Else, match debts by **`Debt.category_id`**.
  3) If multiple debts match a category, allocate **all** to the debt with the **largest principal**.
  4) If the largest principal is tied, **split proportionally** by principal.
- Principal is clamped at **zero** (no negative balances).

## Currency handling in projections
- Projection allocation is performed in **COP** for consistency.
- The allocated COP payment is converted back to the debt currency using the same FX
  rate source as above, so both **principal_original** and **principal_cop** can be updated.

