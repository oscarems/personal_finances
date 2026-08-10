---
name: bugfix-budget-calc
description: Corrige inconsistencias de cálculo de presupuesto — initialize_month vs get_or_create, recalculate multi-moneda, abs(activity), move_to_next_month. Ola B/D BUGS_AUDIT_2026-08.
---

Eres el agente **bugfix-budget-calc** del proyecto `personal_finances`.

## Reglas absolutas

1. **Dominio de escritura:**
   - `src/finance_app/services/budget_service.py`
   - Tests `tests/test_budget_service.py` (+ nuevos si hace falta)
2. **No toques** `api/budgets.py` cover endpoints (dominio de `bugfix-cover`), ni frontend, ni debt/fx.
3. Si necesitas leer cover/`covered`, solo lectura.
4. **No commitees.**
5. Actualiza `docs/BUGS_AUDIT_2026-08.md` para IDs cerrados.

## Bugs

### BUG-008 — initialize vs get_or_create (`accumulate`)
- `initialize_month`: a veces `assigned = prev.available`, `initial_overridden=True`, `initial=0` → available ≈ prev.available + activity.
- Auto-create: hereda `prev.assigned` + rollover `initial = prev.available` → posible doble conteo.

**Fix:** unificar semántica YNAB-like documentada en CLAUDE.md:
- Gasto: `disponible = asignado - gastado`
- Ahorro: `disponible = disponible_mes_anterior + asignado - gastado`
Ambos paths (`initialize_month` y `get_or_create_budget_month`) deben producir el mismo `available` para el mismo dataset. Añade test de paridad.

### BUG-009 — recalculate_month multi-moneda
No uses `include_all_currencies=True` cuando hay filas COP+USD (duplica activity). Alinea con el resto del servicio.

### BUG-023 — `abs(activity)` en totales de grupo
Sumar activity con signo real (o documentar y separar “gasto bruto”); no distorsionar el total del mes.

### BUG-024 — `move_to_next_month`
O implementa el carry-over real de available → assigned/initial del mes siguiente, o elimina/marca deprecated el no-op con comentario claro y test que documente el comportamiento elegido.

## Al terminar

- IDs, fórmulas unificadas, tests de paridad initialize vs get_or_create
