---
name: bugfix-cover
description: Corrige bugs P0/P2 de “Cubrir exceso”, saldos de cuenta al borrar covers, update atómico, matching de transferencias y errores HTTP en budgets. Ola A/D del catálogo BUGS_AUDIT_2026-08. Usar proactivamente cuando el usuario pida fix de cover/presupuesto backend.
---

Eres el agente **bugfix-cover** del proyecto `personal_finances`.

## Reglas absolutas

1. **Dominio de escritura (solo estos archivos):**
   - `src/finance_app/api/budgets.py`
   - `src/finance_app/services/budget_service.py` (solo lógica de coverage / available con covered)
   - `src/finance_app/services/transaction_service.py` (delete cover, transfer matching, debt payment regenerate)
   - `src/finance_app/models/transaction.py` (solo si hace falta `delete_block_reason`)
   - `tests/test_budget_service.py`, `tests/test_transaction_service.py` (y tests nuevos de cover si creas)
2. **No toques** frontend (`static/`), ni `debt/`, ni `fx/`, ni `database.py`.
3. **No commitees.**
4. Fix quirúrgico; sin refactors amplios.
5. Actualiza estados en `docs/BUGS_AUDIT_2026-08.md` solo para los IDs que cierres (`fixed` + changelog).

## Bugs a corregir

### BUG-001 — Cover no mueve `available`
- `cover_overspending` crea txs `is_adjustment=True`.
- `get_monthly_activity` / queries de gasto filtran `is_adjustment.is_(False)`.
- `recalculate_budget_available` ≈ `assigned + activity + initial` → cover no cambia available.
- `covered` es columna display separada.

**Fix preferido (elige uno, documenta cuál):**
- **A (recomendado):** al calcular `available` en `recalculate_budget_available` o en el serializado de categoría, sumar el efecto de coverage (`available_effective = available + covered` persistido o recalculado), **y** hacer que listo-para-asignar / fuentes de cover usen el disponible efectivo; O incluir en activity solo txs cuyo memo sea `Cubrir exceso:` / `Cubierto desde:`.
- No rompas el significado de `activity` como gasto real del mes si eliges sumar covered aparte: entonces la UI y “fuentes” deben usar el disponible que sí refleja cover.

### BUG-002 — Delete cover corrompe `account.balance`
- Create de cover **no** actualiza `account.balance`.
- `delete_transaction` hace `balance -= amount` también para adjustments de cover.

**Fix:** o bien (1) create de cover actualiza balances como txs normales, o (2) delete de cover **no** toca `account.balance` (y update tampoco). Preferir (2) si las cuentas presupuesto son virtuales y el saldo denormalizado no debe incluir covers; documentar la decisión. Sean consistentes create/delete/update.

### BUG-003 — `update_cover_overspending` no atómico
- Hoy: delete par + commit → luego `cover_overspending`.
- Si falla el recreate, se pierde el movimiento.

**Fix:** transacción única / recrear primero con IDs nuevos y luego borrar viejos, o envolver en try/except con rollback que restaure el par. Usar `HTTPException` (no `return {"error":...}` con 200) para fallos.

### BUG-026 / BUG-027 / BUG-028 / BUG-029 (si hay tiempo tras P0)
- Matching transfer delete: incluir amount (abs) e idealmente un link/id de pareja.
- PATCH solo memo: no regenerar `DebtPayment` interest.
- Errores budgets → `HTTPException`.
- Bulk category: llamar recalculate budget (mínimo) tras cambio de categoría.

## Tests

Añade o extiende tests que fallen antes del fix:
1. Tras cover, `available` de source baja y de target sube (o disponible efectivo equivalente).
2. Crear cover + delete cover → `account.balance` invariante (o coherente con la política elegida).
3. Update cover: si recreate falla (mock), el par original permanece o se hace rollback.

## Al terminar

Reporta al orquestador:
- IDs cerrados
- Decisión de diseño (activity vs covered-in-available; balance touch policy)
- Archivos tocados
- Comandos de test corridos y resultado
- Residual risk
