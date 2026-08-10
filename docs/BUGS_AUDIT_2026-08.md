# Auditoría de bugs — 2026-08

Catálogo de defectos hallados en la revisión de backend + frontend.
Estado: `open` | `in_progress` | `fixed` | `wontfix`.

**Orquestación:** ver `docs/SISTEMA_AGENTES.md` § Bugfix y skill `.cursor/skills/bugfix-orchestrator/`.
**Agentes:** `bugfix-cover`, `bugfix-portfolio-fire`, `bugfix-debt-fx`, `bugfix-budget-calc`, `bugfix-fe-ux`.

---

## Ola A — P0 (bloqueantes)

| ID | Severidad | Área | Agente | Estado | Título |
|----|-----------|------|--------|--------|--------|
| BUG-001 | P0 | Presupuesto | `bugfix-cover` | fixed | Cubrir exceso no mueve `available` (txs `is_adjustment` excluidas de activity) |
| BUG-002 | P0 | Presupuesto | `bugfix-cover` | fixed | Borrar cobertura corrompe `account.balance` (create no toca saldo; delete sí) |
| BUG-003 | P0 | Presupuesto | `bugfix-cover` | fixed | `update_cover_overspending` borra+commit antes de recrear → posible pérdida |
| BUG-004 | P0 | Portfolio | `bugfix-portfolio-fire` | fixed | `/portfolio` mount deja spinner; no inyecta HTML |
| BUG-005 | P0 | FIRE | `bugfix-portfolio-fire` | fixed | `/fire` mount deja spinner; no inyecta HTML |
| BUG-006 | P0 | FIRE | `bugfix-portfolio-fire` | fixed | FE lee claves API incorrectas (`fire_ratio` vs `ratio_fire`, etc.) |
| BUG-007 | P0 | Portfolio | `bugfix-portfolio-fire` | fixed | Payload create/price en inglés vs schema español |

### Detalle Ola A

**BUG-001 / BUG-002 / BUG-003** — `api/budgets.py` `cover_overspending`, `transaction_service.delete_transaction`, `get_monthly_activity` filtra `is_adjustment.is_(False)`.
- Fix esperado: que la cobertura afecte `available` (incluir adjustments de cover en activity **o** aplicar `covered` al calcular available); create/delete de cover coherentes con `account.balance`; update atómico (recrear antes de borrar, o rollback).

**BUG-004 / BUG-005** — `static/js/pages/portfolio.js` y `fire.js` `mount()`.
- Fix esperado: inyectar markup completo en `mount` (como otras páginas), luego cargar datos.

**BUG-006 / BUG-007** — contrato FE↔BE.
- Fix esperado: alinear claves y nombres de campos con `fire_service` / schemas de `api/portfolio.py`; preferir español del backend.

---

## Ola B — P1 backend

| ID | Severidad | Área | Agente | Estado | Título |
|----|-----------|------|--------|--------|--------|
| BUG-008 | P1 | Presupuesto | `bugfix-budget-calc` | fixed | `initialize_month` vs `get_or_create_budget_month` discrepantes en `accumulate` |
| BUG-009 | P1 | Presupuesto | `bugfix-budget-calc` | fixed | `recalculate_month` usa `include_all_currencies=True` y puede inflar activity |
| BUG-010 | P1 | Deudas | `bugfix-debt-fx` | fixed | Simulador siempre `monthly/100`; helpers usan heurística `rate > 1` |
| BUG-011 | P1 | Deudas | `bugfix-debt-fx` | fixed | Saldo CC en listados sin conversión FX |
| BUG-012 | P1 | Deudas | `bugfix-debt-fx` | fixed | Amortización no capitaliza interés si cuota < interés |
| BUG-013 | P1 | Migraciones | `bugfix-debt-fx` | fixed | `confirmed_balance*` ausentes de `_MIGRATION_COLUMNS` |
| BUG-014 | P1 | FX | `bugfix-debt-fx` | fixed | Fallo de tasa → identidad 1:1 silenciosa |

---

## Ola C — P1/P2 frontend UX

| ID | Severidad | Área | Agente | Estado | Título |
|----|-----------|------|--------|--------|--------|
| BUG-015 | P1 | Presupuesto FE | `bugfix-fe-ux` | fixed | Race al cambiar de mes sin token/abort |
| BUG-016 | P1 | Presupuesto FE | `bugfix-fe-ux` | fixed | Cambiar moneda no convierte `initial_amount` |
| BUG-017 | P1 | Fechas | `bugfix-fe-ux` | fixed | `toISOString()` UTC → fecha “mañana” de noche (COL) |
| BUG-018 | P1 | Deudas FE | `bugfix-fe-ux` | fixed | `catch` silenciosos en simulator/formulario |
| BUG-019 | P2 | Categorías | `bugfix-fe-ux` | fixed | Checkbox “esencial” ignorado en create |
| BUG-020 | P2 | Transacciones | `bugfix-fe-ux` | fixed | Editar gasto: monto negativo + `min="0"` |
| BUG-021 | P2 | Dashboard | `bugfix-fe-ux` | fixed | Quick-add no refresca vista |
| BUG-022 | P2 | XSS/UX | `bugfix-fe-ux` | fixed | Toast/`onclick` sin escape; tooltips recortados |

---

## Ola D — P2/P3 backend / mejoras

| ID | Severidad | Área | Agente | Estado | Título |
|----|-----------|------|--------|--------|--------|
| BUG-023 | P2 | Presupuesto | `bugfix-budget-calc` | fixed | Totales `activity` con `abs()` distorsionan mes |
| BUG-024 | P2 | Presupuesto | `bugfix-budget-calc` | fixed | `move_to_next_month` no traslada available |
| BUG-025 | P2 | Deudas | `bugfix-debt-fx` | fixed | Proyección “solo mínimo” con mínimo fijo / saldo CC crudo |
| BUG-026 | P2 | Tx | `bugfix-cover` | fixed | Delete transfer: matching frágil (solo fecha+cuentas) |
| BUG-027 | P2 | Tx | `bugfix-cover` | fixed | PATCH memo regenera DebtPayment con interés re-estimado |
| BUG-028 | P2 | API | `bugfix-cover` | fixed | Budgets/API: errores como JSON 200 |
| BUG-029 | P2 | API | `bugfix-cover` | fixed | Bulk category update sin recalcular budget/debt |
| BUG-030 | P3 | FX | `bugfix-debt-fx` | fixed | Converter presupuesto solo USD↔COP |
| BUG-031 | P3 | Deudas | `bugfix-debt-fx` | fixed | Unificar unidades de tasa; documentar |
| BUG-032 | P3 | FE | `bugfix-portfolio-fire` | fixed | Unificar cliente API `/api` vs `/api/v1` |

---

## Cómo marcar un fix

1. El agente asignado implementa y reporta archivos tocados + tests.
2. Orquestador corre `verifier` (gate bugfix).
3. Actualizar esta tabla: `Estado = fixed` y añadir nota en § Changelog abajo.
4. Commit único por ola (no por bug suelto, salvo P0 urgentes).

## Changelog

| Fecha | IDs | Nota |
|-------|-----|------|
| 2026-08-10 | BUG-025, BUG-030 | Cost-analysis: mínimo dinámico por saldo declinante + saldo CC FX; budget `_make_currency_converter*` documenta USD↔COP y usa `convert_currency` cuando hay `db` |
| 2026-08-10 | BUG-026…029 | Transfer pair `import_id` + match por abs(amount); PATCH memo no regenera DebtPayment; budgets → HTTPException; bulk category recalcula budget + debt reverse/apply |
| 2026-08-10 | BUG-015…022 | FE UX: race token mes budget; FX convierte `initial_amount`; `todayISO`/daysAgo locales; toast/optional en deudas; `is_essential` en create; monto abs en edit; dashboard remount post quick-add; toast escape + tooltip overflow |
| 2026-08-10 | BUG-010…014, BUG-031 | Debt/FX: simulator→`effective_monthly_interest_rate`; CC saldo con FX; capitaliza interés en engine; migraciones `confirmed_balance*`; FX `RateResult`/`ConversionResult` + warning (no 1:1 silencioso); unidades documentadas (>1 %=decimal) |
| 2026-08-10 | BUG-008, 009, 023, 024 | Budget calc: accumulate = prev.available+assigned+activity+coverage (paridad initialize/get_or_create); recalculate_month multi-moneda; activity firmado; move_to_next_month carry-over real |
| 2026-08-10 | BUG-001, BUG-002, BUG-003 | Cover: `available` = assigned+activity+coverage_net; create/delete cover no tocan `account.balance`; update atómico + HTTPException |
| 2026-08-10 | BUG-004…007, BUG-032 | `portfolio.js`/`fire.js` shell en mount; claves FIRE ES; create/price ES; `client.js` portfolio/fire `/v1` |
| 2026-08-10 | BUG-001…032 | Catálogo inicial tras auditoría |
