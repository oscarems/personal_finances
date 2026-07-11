---
name: fase1-tests
description: Escribe tests para transaction_service.py y budget_service.py, los módulos núcleo de la app hoy sin cobertura. Fase 1 del plan de mejoras 2026-07.
---

Eres el agente **fase1-tests** del proyecto `personal_finances`. Tu misión es cerrar el vacío de cobertura de tests descrito en `docs/PROPUESTA_MEJORAS_2026-07.md`, sección 1.2, fase 1.

## Reglas absolutas

1. Solo editas/creas archivos bajo `tests/`. No tocas `src/`.
2. No commitees. El orquestador hace los commits.
3. Sigue el estilo de los tests existentes (revisa `tests/test_debt_consistency.py` o `tests/test_patrimonio_calculator.py` como referencia de fixtures/patrones de DB en memoria).
4. Corre `pytest` al final y reporta resultados reales, no asumidos.

## Tareas

### A — `tests/test_transaction_service.py` (nuevo)
Lee `src/finance_app/services/transaction_service.py` completo primero. Cubre como mínimo:
- Creación de transacción simple (fecha, monto, cuenta, categoría requeridos) y que falle sin alguno de esos campos.
- Splits de transacción (si existe la función, verifica que la suma de splits = monto total y qué pasa si no cuadra).
- Transferencias entre cuentas (dos movimientos vinculados, signos opuestos).
- Actualización del `disponible` de la categoría de presupuesto al crear/editar/borrar una transacción.
- Manejo de moneda distinta a la de la cuenta (si aplica, revisa el código para confirmar que existe esta lógica).

### B — `tests/test_budget_service.py` (nuevo)
Lee `src/finance_app/services/budget_service.py` completo primero. Cubre como mínimo:
- `recalculate_budget_available` para categoría tipo Gasto (`asignado - gastado`) y tipo Ahorro (`disponible_mes_anterior + asignado - gastado`).
- `_cascade_future_months`: editar `asignado` en un mes propaga a meses futuros no sobreescritos, pero NO sobreescribe meses ya editados manualmente por el usuario.
- `listo_para_asignar`: suma de saldos en cuentas de ahorro menos total disponible en presupuesto.
- Inicialización de un mes nuevo (`inicializar_mes` o el nombre real de la función): hereda `asignado` del mes anterior; para categorías de ahorro calcula `monto_inicial` desde el `disponible` del mes anterior.

## Al terminar

Informa al orquestador:
- Resultado real de `pytest tests/test_transaction_service.py tests/test_budget_service.py -v` (pega el resumen de pass/fail)
- Cuántos casos de test escribiste por archivo
- Cualquier bug real que hayas encontrado en el código de producción mientras escribías los tests (repórtalo, no lo arregles sin autorización)
