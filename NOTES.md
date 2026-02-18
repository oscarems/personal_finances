# Auditoría de deuda/hipoteca y plan de cambios

## Hallazgos

1. **Cálculo duplicado y divergente**
   - `src/finance_app/services/debt_balance_service.py` y `src/finance_app/services/debt_amortization_service.py` calculaban saldos con reglas distintas.
   - `debt_amortization_service` tenía `accrue_interest=False`, ignorando interés para proyecciones.
   - `src/finance_app/api/reports.py` y `src/finance_app/api/debts.py` consumían resultados de caminos distintos.

2. **Parámetros de deuda**
   - Se almacenan en `debts`: `original_amount`, `current_balance`, `interest_rate`, `annual_interest_rate`, `term_months`, `loan_years`, `start_date`, `payment_day`.
   - No existe una columna dedicada a `amortization_type`; hoy se infiere por `debt_type` o notas.

3. **Pagos reales**
   - Existe enlace directo en `debt_payments.debt_id`.
   - Para hipoteca existe `mortgage_payment_allocations` (`transaction_id` + `loan_id`).
   - Transacciones generales (`transactions`) no tienen `debt_id`; por eso se agregó fallback heurístico por categoría/cuenta/texto.

4. **Convención de tasa**
   - `mortgage_service` y la documentación interna describen tasa **efectiva anual** con conversión mensual `(1+r)^(1/12)-1`.

## Plan ejecutado

- Crear `AmortizationEngine` único con API:
  - `generate_schedule(debt, as_of=None, mode="plan|actual|hybrid")`
  - `balance_as_of(debt, date, mode=...)`
- Soportar tipos de cuota mínimos:
  - cuota fija (francés), capital fijo (alemán), solo interés.
- Integrar pagos extra (principal real > principal plan) para reducir plazo.
- Refactorizar servicios consumidores para usar engine único (Deudas + Patrimonio vía amortización mensual).
- Exponer endpoint de cronograma en Deudas: `GET /api/debts/{debt_id}/schedule`.
- Agregar tests unitarios críticos de amortización y redondeo.

## Limitaciones actuales

- La app aún no tiene UI para asignar manualmente una transacción a una deuda cuando no hay link directo.
- El fallback heurístico aplica sólo si no hay `debt_payments` ni `mortgage_payment_allocations`.
