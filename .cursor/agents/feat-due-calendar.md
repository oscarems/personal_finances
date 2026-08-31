---
name: feat-due-calendar
description: Página calendario de vencimientos reusando cash-flow upcoming. Ola C UX_PRODUCT_AUDIT.
---

Eres el agente **feat-due-calendar** del proyecto `personal_finances`.

## Reglas absolutas

1. **Dominio de escritura:**
   - `src/finance_app/static/js/pages/calendar.js` (crear)
   - `src/finance_app/static/js/app.js` — solo `register('/calendar', ...)` + ítem en grupo **Hoy** (o Plan)
   - `src/finance_app/static/js/api/client.js` — solo si falta alias; preferir `cashFlow.upcoming` existente
   - `docs/UX_PRODUCT_AUDIT_2026-08.md` (UX-006)
2. Backend: **no inventes tabla nueva**. Usa `GET /cash-flow/upcoming?days=30`. Si necesitas enriquecer con billing-cycle, hazlo en FE con `debts.list` + campos ya presentes, o un endpoint delgado en `api/cash_flow.py` **solo** si es imprescindible (entonces también `app.py` include si aplica — ya está montado).
3. **No commitees.**
4. UI: `pageState`, `emptyState`, español, design system light.

## Tareas — UX-006

1. Página `/calendar`: header “Vencimientos”, filtro días (7/14/30), lista agrupada por fecha.
2. Cada evento: label, tipo/source badge, monto `amount`, link contextual (`/recurring`, `/debts`, `/cash-flow`).
3. Loading / error+retry / empty (“No hay vencimientos en este periodo”).
4. Registrar ruta y nav.

## Al terminar

Ruta, endpoint, estados, smoke mental del render vacío y con eventos.
