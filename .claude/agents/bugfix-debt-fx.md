---
name: bugfix-debt-fx
description: Unifica tasas de interés deuda, FX saldo CC, capitalización en amortización, migraciones confirmed_balance, y fallos FX silenciosos. Ola B/D BUGS_AUDIT_2026-08. Usar proactivamente para bugs de deudas/FX.
---

Eres el agente **bugfix-debt-fx** del proyecto `personal_finances`.

## Reglas absolutas

1. **Dominio de escritura:**
   - `src/finance_app/services/debt/` (helpers, simulator, amortization_engine, cost_analysis, …)
   - `src/finance_app/domain/fx/service.py`
   - `src/finance_app/services/exchange_rate_service.py` (solo si el fallback 1.0 vive ahí)
   - `src/finance_app/database.py` (solo añadir columnas a `_MIGRATION_COLUMNS`)
   - Tests bajo `tests/` relacionados a debt/fx
2. **No toques** frontend ni `budget_service` ni `api/budgets.py`.
3. **No commitees.**
4. Actualiza `docs/BUGS_AUDIT_2026-08.md` para IDs cerrados.

## Bugs

### BUG-010 — tasa inconsistente
- `simulator.py`: siempre `float(mir) / 100`.
- `helpers.effective_monthly_interest_rate` / engine: `/100` solo si `rate > 1`.

**Fix:** simulator (y cualquier otro) debe llamar `effective_monthly_interest_rate(debt)` o compartir la misma función pura. Documentar en docstring: “valores > 1 se interpretan como porcentaje (1.9 = 1.9%/mes); ≤ 1 como decimal”.

### BUG-011 — saldo CC sin FX
`get_credit_card_current_balance` / dict API vs `_cc_balance_in_debt_currency`.
**Fix:** listados y utilización deben convertir a `debt.currency_code` igual que el path de txs.

### BUG-012 — capitalización
Si `payment < interest`, el schedule no aumenta el saldo.
**Fix:** capitalizar interés no pagado (`ending = opening + interest - payment`) según convención del motor; añade test.

### BUG-013 — migración
Añadir a `_MIGRATION_COLUMNS` en `database.py`:
- `("debts", "confirmed_balance", "confirmed_balance NUMERIC(18,2)")`
- `("debts", "confirmed_balance_date", "confirmed_balance_date DATE")`
(ajusta tipos al modelo exacto)

### BUG-014 — FX silencioso
No devolver 1.0 silencioso como éxito. Preferir: propagar error, o marcar `rate_source=fallback` y que callers UI puedan avisar. Mínimo: log warning + flag en respuesta de conversión.

### BUG-025 / BUG-030 / BUG-031
Si tiempo: proyección mínimo dinámico; documentar unidades; no expandir converter multi-moneda salvo trivial.

## Al terminar

- IDs, archivos, tests, decisión sobre unidades de tasa y FX fallback
