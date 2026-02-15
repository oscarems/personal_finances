# Auditoría Integral SSOT de Deuda (Principal Engineer + QA)

## 1) Resumen ejecutivo

1. El repositorio ya tiene piezas de dominio para deuda (`src/domain/debts/*`) y servicios operacionales (`src/finance_app/services/*`), pero **no existe una API interna única** con contrato explícito tipo `calculate_debt_balance(debt_id, as_of_date, base_currency=...)` que sea consumida por todas las vistas.
2. Hay múltiples motores de cálculo activos para saldos de deuda: `debt_balance_service`, `debt_amortization_service`, `domain/debts/service`, y lógica embebida en `api/debts.py`/`api/reports.py`.
3. `debt_amortization_service` actualmente fuerza `accrue_interest = False` para todas las deudas, lo que puede desalinear principal esperado vs deuda real para créditos con interés.
4. `domain/debts/service.get_debts_principal` usa `debt.current_balance` para `credit_loan`/`credit_card` y solo recalcula hipoteca, por lo que no coincide siempre con `calculate_debt_balance_as_of`.
5. La UI de deudas (`/debts`) y patrimonio (`/patrimonio`) consume endpoints distintos (`/api/debts*` vs `/api/reports/net-worth`) que no usan exactamente el mismo camino de cálculo.
6. Multi-moneda: hay dos rutas de conversión distintas (`domain.fx.convert_to_cop` con histórico y fallback, y `reports.convert_to_currency` con una sola tasa “latest”), lo que puede introducir discrepancias por fecha.
7. El simulador de hipoteca (`/api/mortgage/*`) es puro cálculo y **no muta deuda real**, lo cual cumple el requisito crítico de “simulado ≠ real salvo aplicar explícitamente”.
8. Las mutaciones de deuda real por transacciones/recurrencias sí ocurren automáticamente y actualizan `debt.current_balance`; esto convive con cálculos derivados, elevando riesgo de drift.
9. Existen checks de mismatch (`_log_debt_mismatch`) en reportes, evidencia de inconsistencia conocida entre “legacy” y “canonical” dentro del sistema.
10. Recomendación principal: centralizar en un único motor de dominio con salida dual (moneda original + convertida para reporting) y migrar endpoint por endpoint.

---

## 2) Hallazgos por severidad

### Critical

- **No hay SSOT único operativo para “saldo de deuda”.**
  - Evidencia: coexisten `calculate_debt_balance_as_of` (servicio), `ensure_debt_amortization_records` (tabla derivada mensual), `get_debts_principal` (dominio), y lógica de resumen en APIs.
- **`debt_amortization_service` ignora interés al proyectar/calcular (`accrue_interest = False`) incluso para deudas con tasa.**
  - Impacto: reportes pueden subestimar pasivos o no reflejar cronograma real.
- **`domain/debts/service` no recalcula `credit_loan` (usa `current_balance`), mientras otros caminos sí recalculan/proyectan.**
  - Impacto: “mismo `debt_id`” puede dar valores diferentes por endpoint/contexto.

### High

- **Conversión de moneda inconsistente por fecha/fuente.**
  - `domain.fx.convert_to_cop` usa tasa histórica por fecha con fallback ordenado.
  - `api/reports.convert_to_currency` usa una tasa “latest” global (`get_exchange_rate`).
- **Mutación directa de `debt.current_balance` en servicios transaccionales y recurrentes, con reglas simplificadas de principal/interés para no-hipoteca.**
  - Riesgo de separar “dato almacenado” vs “dato derivado” sin reconciliación fuerte.

### Medium

- **Duplicación de helpers financieros (`_annual_rate_decimal`, `_monthly_rate`, iteradores mensuales) en varios módulos.**
- **Endpoint `/api/debts/summary` mezcla cálculo por amortización + scheduled + current_balance fallback, aumentando caminos.**
- **Checks de mismatch existen pero no bloquean ni corrigen.**

### Low

- **Documentación de deuda no refleja totalmente todos los caminos vivos (domain, amortization, transacciones automáticas).**
- **No hay contrato formal de redondeo homogéneo para todos los endpoints (algunos `round(2)`, otros `Decimal quantize`).**

---

## 3) Mapa del sistema (módulos y flujos de datos)

### Módulos/paquetes principales

- `src/finance_app/models/*`: ORM SQLAlchemy (Debt, DebtPayment, DebtAmortizationMonthly, DebtSnapshotMonthly, ExchangeRate, etc.).
- `src/finance_app/services/*`: lógica operacional (deuda, amortización, transacciones, hipoteca, FX de app).
- `src/domain/debts/*`: capa de dominio para principal de deuda, snapshots y proyecciones por pagos programados.
- `src/domain/fx/*`: conversión a COP basada en tabla histórica + fallback.
- `src/finance_app/api/*`: routers REST (deudas, reportes, hipoteca, etc.).
- `src/finance_app/templates/*`: UI Jinja + JS que consume endpoints.

### Flujo de datos (BD -> dominio/servicio -> API -> UI)

1. **BD (SQLite/SQLAlchemy models)**
   - Tablas fuente: `debts`, `debt_payments`, `mortgage_payment_allocations`, `exchange_rates`, etc.
2. **Dominio/Servicios**
   - Cálculo deuda: `debt_balance_service`, `debt_amortization_service`, `domain/debts/service`.
   - FX: `domain/fx/service` y helper de `reports`.
3. **API**
   - `/api/debts`, `/api/debts/summary`, `/api/reports/debt-*`, `/api/reports/net-worth`.
4. **UI**
   - `debts.html` consume `/api/debts/` y `/api/debts/summary`.
   - `wealth.html` consume `/api/reports/net-worth` y opciones de hipotecas desde `/api/debts?...`.

---

## 4) Auditoría SSOT de deudas

### Tabla: Lugar del cálculo -> Clasificación -> Recomendación

| Lugar del cálculo/almacenamiento | Clasificación | Evidencia | Recomendación |
|---|---|---|---|
| `services/debt_balance_service.py::calculate_debt_balance_as_of` | **Cálculo canonical candidato** | Recalcula por fecha usando pagos y reglas por tipo de deuda. | Convertirlo en motor oficial detrás de API única por `debt_id`. |
| `services/debt_amortization_service.py::ensure_debt_amortization_records` + tabla `debt_amortization_monthly` | **Derivado (cache materializada) + riesgoso** | Precalcula `principal_remaining`, pero con `accrue_interest = False`. | Mantener como proyección/cache, nunca fuente principal; alinear con motor único. |
| `domain/debts/service.py::get_debts_principal` | **Duplicado / bug probable** | Para no-hipoteca usa `debt.current_balance` en vez de motor común. | Reemplazar por llamada unificada al motor central para todos los tipos. |
| `api/debts.py::_debt_to_dict_with_calculated_balance` | **Derivado** | Mezcla `credit_card` passthrough y scheduled para `mortgage/credit_loan`. | Consumir API interna única y devolver saldo canonical + metadata. |
| `api/reports.py::get_debt_balance_history` | **Derivado** | Usa amortización mensual + conversión a COP por mes. | Leer balance canonical (por mes) vía motor único y convertir solo al reportar. |
| `api/reports.py::get_net_worth` | **Derivado / riesgoso** | Mezcla mortgage directa + amortización + fallback tarjeta. | Unificar liabilities via API interna única por deuda/mes. |
| `api/reports.py::get_debt_summary` | **Derivado / duplicado** | Cálculo separado de current/projected por tipo. | Reusar motor único + wrapper de proyección. |
| `services/transaction_service.py` y `services/recurring_service.py` mutando `debt.current_balance` | **Riesgoso** | Actualizan saldo almacenado por evento con reglas simplificadas. | Mantener mutación de estado real, pero reconciliar con motor en post-write check. |
| `domain/fx/service.py::convert_to_cop` | **Canonical FX candidato (reporting)** | Usa tasa histórica por fecha + fallback jerárquico. | Estandarizar toda conversión de reportes en este módulo. |
| `api/reports.py::convert_to_currency` + `get_exchange_rate` | **Duplicado / riesgoso** | Usa tasa única latest, no siempre histórica por fecha. | Migrar a `domain.fx` (o un `fx_port`) con as_of_date obligatorio. |

### Lugares donde se guarda saldo de deuda

- **Fuente persistida primaria actual:** `debts.current_balance` (y para hipoteca también `principal_balance`, `interest_balance`).
- **Derivados persistidos:** `debt_amortization_monthly.principal_remaining`, `debt_snapshots_monthly.principal_original/principal_cop`.
- **Riesgo SSOT:** coexistencia de saldo persistido + múltiples derivados + múltiples motores de cálculo sin contrato de precedencia único.

### Reportes de patrimonio (net worth)

- La liability se calcula en `get_net_worth` mezclando tres caminos (mortgage directa, amortización, fallback de tarjeta), luego convierte moneda para salida.
- Recomendación: liability mensual por cada `debt_id` = llamada única al motor central + conversión de presentación.

---

## 5) Diseño objetivo (Target Design)

### API interna única propuesta

```python
calculate_debt_balance(
    debt_id: int,
    as_of_date: date,
    base_currency: str = "COP",
    include_projection: bool = False,
) -> DebtBalanceResult
```

### Inputs

- `debt_id` (obligatorio)
- `as_of_date` (fecha de corte)
- `base_currency` (solo para reporting; cálculo core siempre en moneda original)
- Datos fuente:
  - `Debt.original_amount`, `Debt.start_date`, `Debt.debt_type`
  - `DebtPayment` (principal/interés/fees; si `principal is None`, inferir por `amount-interest-fees`)
  - `MortgagePaymentAllocation` (principal/extra principal/interés/fees/escrow)
  - Parámetros de deuda (`interest_rate`, `annual_interest_rate`, `monthly_payment`, `term_months/loan_years`)
  - FX por fecha (`ExchangeRate` o fallback definido)

### Outputs

- `debt_id`, `as_of_date`, `status` (open/closed)
- `original_currency`
- `principal_original` (**SSOT**)
- `interest_accrued_original` (si aplica)
- `fees_accrued_original` (si aplica)
- `principal_paid_to_date_original`, `interest_paid_to_date_original`
- `reporting`: `{ base_currency, principal_base, interest_base, fx_rate_used, fx_source, fx_as_of_date }`
- `explain`: vector opcional de eventos aplicados (para trazabilidad QA)

### Reglas de negocio explícitas

1. **SSOT = principal en moneda original.**
2. **Conversión de moneda solo al final (presentación/reporting).**
3. **Prioridad de pagos:** fees -> interest -> principal, salvo asignación explícita manual.
4. **Fecha de corte:** incluir pagos con `payment_date <= as_of_date`; futuros no afectan saldo real.
5. **Proyección (`include_projection=True`)** usa únicamente pagos programados configurados; nunca muta DB real.
6. **Hipoteca simulada** (`/api/mortgage/*`) no muta deuda real; mutación solo por acción explícita “aplicar”.
7. **Redondeo:** cálculo interno en `Decimal` (precision alta), salida monetaria con cuantización por moneda (COP 2 dec o regla de `Currency.decimals`).

---

## 6) Plan de refactor incremental (PR por PR, sin romper producción)

### PR-1: Introducir motor central sin cambiar comportamiento

- **Objetivo:** crear `DebtBalanceEngine` con API `calculate_debt_balance(...)` y adaptador backward-compatible.
- **Archivos a tocar (mínimo):**
  - `src/finance_app/services/debt_balance_service.py` (extraer motor/contrato)
  - `src/domain/debts/service.py` (consumir adaptador)
  - `src/domain/debts/types.py` (nuevo result DTO)
- **Riesgos:** divergencia por rounding y fechas de corte; mitigación con golden tests comparativos contra salidas actuales.

### PR-2: Migrar vistas/endpoints gradualmente

- **Objetivo:** `api/debts.py` y `api/reports.py` pasan a leer solo del motor.
- **Archivos:**
  - `src/finance_app/api/debts.py`
  - `src/finance_app/api/reports.py`
  - `src/finance_app/templates/debts.html` (si cambia contrato JSON)
  - `src/finance_app/templates/wealth.html` (si cambia payload)
- **Riesgos:** contratos JSON y performance por recalcular mensual; mitigación con cache de consulta por request.

### PR-3: Consolidar FX y eliminar duplicaciones

- **Objetivo:** deprecate `reports.convert_to_currency` y usar un único servicio FX con `as_of_date`.
- **Archivos:**
  - `src/finance_app/api/reports.py`
  - `src/domain/fx/service.py`
  - posibles adaptadores en `src/finance_app/services/currency_service.py`
- **Riesgos:** cambios en números históricos; mitigación con snapshots de regresión por mes/moneda.

### PR-4: Eliminar lógica duplicada + endurecer invariantes

- **Objetivo:** remover cálculos legacy y convertir `debt_amortization_monthly` en cache derivado explícito del motor.
- **Archivos:**
  - `src/finance_app/services/debt_amortization_service.py`
  - `src/domain/debts/projection.py`
  - `src/domain/debts/snapshot.py`
- **Riesgos:** dependencia de jobs/cron; mitigación con feature flag de “read-from-engine”.

### PR-5: Cobertura de tests de consistencia end-to-end

- **Objetivo:** test matrix completa para SSOT + multicurrency + simulación vs real.
- **Archivos:**
  - `tests/test_debt_consistency.py`
  - `tests/test_reports_wealth.py`
  - nuevos: `tests/test_debt_balance_engine.py`, `tests/test_debt_engine_currency.py`, `tests/test_debt_engine_mortgage_simulation.py`
- **Riesgos:** tests frágiles por fecha actual; mitigación fijando `today` en fixtures.

---

## 7) Tests obligatorios recomendados

### Unit tests del motor central

1. `test_engine_no_payments_keeps_original_principal`
   - Sin pagos: saldo = principal inicial al corte.
2. `test_engine_partial_payment_reduces_only_principal_component`
   - Pago parcial con interés/fees explícitos.
3. `test_engine_early_payment_applies_before_due_schedule`
   - Pago adelantado afecta saldo a la fecha.
4. `test_engine_future_payment_not_included_before_as_of`
   - Pago futuro no impacta corte actual.
5. `test_engine_multi_currency_original_unchanged_reporting_converted`
   - SSOT en moneda original, conversión solo salida.
6. `test_engine_uses_historical_rate_as_of_date`
   - Verifica tasa por fecha (no latest global).
7. `test_engine_mortgage_simulation_does_not_mutate_real_debt`
   - Simulación devuelve resultado sin `db.commit` implícito.
8. `test_engine_apply_action_mutates_real_debt_explicitly`
   - Solo acción explícita persiste cambio.

### Tests de consistencia cross-view

9. `test_same_debt_id_same_balance_across_debts_and_reports`
   - `/api/debts`, `/api/reports/debt-summary`, `/api/reports/net-worth` alineados.
10. `test_total_liabilities_equals_sum_engine_balances`
   - Patrimonio liabilities == suma engine por mes.
11. `test_debt_balance_history_matches_engine_monthly_snapshots`
   - Historial mensual igual a resultados del motor por corte.
12. `test_projection_flag_does_not_change_current_real_balance`
   - Proyección solo lectura.

---

## 8) Gaps explícitos (sin inventar)

1. **Gap de contrato:** no existe hoy la API interna única solicitada por firma (`debt_id` + `base_currency`).
   - **Adición mínima:** nuevo servicio `debt_balance_engine.py` + DTO `DebtBalanceResult`.
2. **Gap de consistencia FX:** no hay un único conversor con `as_of_date` obligatorio para todo reporting.
   - **Adición mínima:** wrapper único `convert_amount(amount, from_code, to_code, as_of_date)`.
3. **Gap de simulación/aplicación explícita para hipoteca real:** simulador existe pero no endpoint “apply scenario to debt”.
   - **Adición mínima:** endpoint explícito transaccional (opt-in) con auditoría.
4. **Gap de test matrix completa:** hay tests parciales de consistencia y reportes, pero no cubren todos los casos borde exigidos.
   - **Adición mínima:** suite dedicada al motor central + consistencia de vistas.
