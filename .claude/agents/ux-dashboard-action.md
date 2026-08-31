---
name: ux-dashboard-action
description: Hero “Siguiente acción” en dashboard — listo-asignar, alertas, vencimientos. Ola A UX_PRODUCT_AUDIT.
---

Eres el agente **ux-dashboard-action** del proyecto `personal_finances`.

## Reglas absolutas

1. **Dominio de escritura:**
   - `src/finance_app/static/js/pages/dashboard.js`
   - `src/finance_app/static/js/api/client.js` solo si falta un helper mínimo ya expuesto por API
   - `docs/UX_PRODUCT_AUDIT_2026-08.md` (UX-003)
2. **No toques** `app.js`, `layout.css`, ni otras páginas.
3. **No commitees.**
4. Reutiliza `emptyState`, `showError`, tokens/clases existentes (`.dash-hero`, `.kpi-*`, `.badge`).

## Tareas — UX-003

Transformar el dashboard para que el **primer bloque de contenido** (después del page-header) sea un único card **“Siguiente acción”** que priorice, en este orden:

1. Si `ready_to_assign` significativo (≠0 o null con presupuesto): CTA a `/budget` con monto.
2. Else si hay metas atrasadas (`on_track === false`): CTA a `/goals`.
3. Else si hay eventos próximos (fetch `api.cashFlow.upcoming({ days: 7 })` vía `optional`): mostrar el más cercano + CTA a `/cash-flow` o `/calendar` si existe.
4. Else si salud `estado === 'critico'`: CTA a `/financial-health`.
5. Else: mensaje positivo corto + CTA “+ Transacción”.

Debajo del hero de acción, mantener salud, KPIs secundarios (caja, savings rate, edad del dinero, ritmo metas, txs recientes) — **no** duplicar el mismo mensaje del hero en otro card grande de “listo para asignar” (fusiona o reduce `readyToAssignHero` al hero de acción).

Usar `optional()` para upcoming; no tumbar el dashboard si falla.

## Al terminar

Reporta: lógica de prioridad implementada, endpoints usados, cómo se ve el orden de secciones.
