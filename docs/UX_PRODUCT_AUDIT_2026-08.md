# UX / Producto — Catálogo de agentes (2026-08)

Fuente de verdad para el sistema de agentes **ux-*** / **feat-*** derivado del análisis experto (gaps + UI/UX).
Complementa `docs/ROADMAP_FASES.md` (Fases 4–5) y `docs/SISTEMA_AGENTES.md`.

**Regla:** no se mezclan dominios de archivo entre agentes concurrentes. Commit solo si el usuario lo pide.

---

## Olas

| Ola | Agentes (paralelo) | IDs |
|-----|--------------------|-----|
| A (shell UX) | `ux-nav-ia` \|\| `ux-dashboard-action` | UX-001…003 |
| B (consistencia) | `ux-page-states` \|\| `ux-mobile` | UX-004…005 |
| C (producto) | `feat-due-calendar` | UX-006 |
| D (diferido) | backlog sin agentes aún | UX-007…010 |

---

## Catálogo

| ID | Severidad | Agente | Estado | Resumen |
|----|-----------|--------|--------|---------|
| UX-001 | P0 | ux-nav-ia | fixed | Reagrupar sidebar: Hoy / Plan / Análisis / Más (colapsar simuladores) |
| UX-002 | P0 | ux-nav-ia | fixed | Registrar ruta `/email-sender-rules` + ítem nav si aplica |
| UX-003 | P0 | ux-dashboard-action | fixed | Hero “Siguiente acción”: listo-asignar + alertas + vencimientos próximos |
| UX-004 | P1 | ux-page-states | fixed | Unificar `pageState`/`emptyState` en goals, patrimonio, income, recurring, setup, gmail, email-rules |
| UX-005 | P1 | ux-mobile | fixed | Tablas → cards / overflow; CTA sticky en txs/presupuesto &lt;768px |
| UX-006 | P1 | feat-due-calendar | fixed | Página `/calendar` con vencimientos (reusa `/cash-flow/upcoming` + ciclos TC) |
| UX-007 | P2 | — | backlog | Reporte esencial vs discrecional (semáforo) |
| UX-008 | P2 | — | backlog | UI CRUD AlertRule |
| UX-009 | P2 | — | backlog | Fase 4 inversiones (dividendos, rebalanceo, FIFO) — ver ROADMAP |
| UX-010 | P2 | — | backlog | Fase 5 resto (undo, adjuntos, PWA, onboarding) |

---

## Criterios de aceptación por ola

### Ola A
- [x] Sidebar tiene ≤4 grupos; simuladores viven bajo “Más” / “Herramientas”.
- [x] Link setup → reglas de email abre página real.
- [x] Dashboard muestra un bloque único de “próxima acción” arriba de KPIs secundarios.

### Ola B
- [x] Páginas listadas usan `showError` / `loadingState` de `pageState.js` (no `alert-danger` crudo sin retry).
- [x] En viewport &lt;768px, tablas principales no desbordan horizontalmente sin scroll controlado; hay CTA sticky en presupuesto/transacciones.

### Ola C
- [x] Ruta `/calendar` en nav (grupo Hoy o Plan).
- [x] Lista eventos próximos 30 días con tipo (recurrente / deuda / cuota) y deep-link.

---

## Changelog

| Fecha | Evento |
|-------|--------|
| 2026-08-20 | Catálogo creado. Sistema de agentes UX/producto definido. |
| 2026-08-20 | UX-001/002 fixed: sidebar Hoy/Plan/Análisis/Más + ruta `/email-sender-rules`. |
| 2026-08-20 | UX-003 fixed: hero “Siguiente acción” en dashboard con prioridad listo-asignar → metas → vencimientos → salud crítica → positivo. |
| 2026-08-20 | UX-004 fixed: `pageState`/`emptyState` unificados en goals, patrimonio, income, recurring, setup, gmail-import, email-rules. |
| 2026-08-20 | UX-005 fixed: overflow-x en tablas mobile, `.list-row` táctil, CTA sticky (`page-with-sticky-cta` / `sticky-page-cta`) en presupuesto y transacciones. |
| 2026-08-20 | UX-006 fixed: página `/calendar` (Vencimientos) con filtro 7/14/30 días, agrupación por fecha, badges tipo/fuente y deep-links a recurrentes/deudas/flujo de caja. |
