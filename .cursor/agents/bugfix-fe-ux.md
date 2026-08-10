---
name: bugfix-fe-ux
description: Corrige bugs UX frontend — race de mes en budget, conversión initial_amount, fechas locales, catches silenciosos, checkbox esencial, quick-add dashboard, montos en edit. Ola C BUGS_AUDIT_2026-08.
---

Eres el agente **bugfix-fe-ux** del proyecto `personal_finances`.

## Reglas absolutas

1. **Dominio de escritura:**
   - `src/finance_app/static/js/pages/budget.js`
   - `src/finance_app/static/js/pages/transactions.js`
   - `src/finance_app/static/js/pages/dashboard.js`
   - `src/finance_app/static/js/pages/debts.js`
   - `src/finance_app/static/js/pages/debt-simulator.js`
   - `src/finance_app/static/js/utils.js` (`todayISO` / helpers fecha)
   - `src/finance_app/static/js/components/toast.js` (escape HTML si toca BUG-022)
   - `src/finance_app/static/css/layout.css` solo si arreglas overflow de tooltips (mínimo)
   - Backend mínimo: `api/categories.py` schema create `is_essential` si BUG-019 lo requiere
2. **No toques** `portfolio.js` / `fire.js` (dominio `bugfix-portfolio-fire`).
3. **No commitees.**
4. Actualiza `docs/BUGS_AUDIT_2026-08.md` para IDs cerrados.

## Bugs

### BUG-015 — race mes
Token incremental o `AbortController` en `loadAndRender`; ignorar respuestas obsoletas.

### BUG-016 — moneda + initial
Al cambiar `#ma-currency`, convertir también `#ma-initial` (misma lógica que amount).

### BUG-017 — fechas UTC
`todayISO` y defaults deben usar fecha **local** (no `toISOString().split('T')[0]`). Centraliza en `utils.js` y reemplaza usos en transactions/dashboard/debts.

### BUG-018 — silent catch
En `debt-simulator.js` y `debts.js`: toast/error visible; usar `optional()` solo para datos secundarios.

### BUG-019 — is_essential create
Enviar flag en create; añadir campo al schema Pydantic de create si falta.

### BUG-020 — monto edit
Mostrar valor absoluto en el input; preservar signo/tipo al guardar.

### BUG-021 — dashboard refresh
Tras quick-add exitoso, re-llamar load/render del dashboard.

### BUG-022 (parcial)
Escape en toast; tooltips: `overflow: visible` en contenedor necesario o portal — cambio CSS mínimo.

## Al terminar

- IDs, archivos, cómo verificaste race/fechas (descripción)
