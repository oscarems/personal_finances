# Roadmap por fases — Features faltantes

Documento vivo del plan de features que el proyecto aún no tiene (o tiene a medias).
**Regla de avance:** no se inicia la fase N+1 hasta aprobación explícita de la fase N.

Última actualización: 2026-08-12  
Origen: análisis experto vs estado real del código (no solo docs legacy).

---

## Estado global

| Fase | Nombre | Estado |
|------|--------|--------|
| 1 | Base diaria | ✅ Aprobada |
| 2 | Control y proyección | ✅ Aprobada |
| 3 | Metas y “qué pasa si” | ✅ Implementada — esperando aprobación |
| 4 | Inversiones / FIRE | ⏳ Pendiente |
| 5 | Producto y operación | ⏳ Pendiente |
| 6 | Nice-to-have | ⏳ Pendiente |

**Fuera de alcance (decisión del usuario):** importador CSV bancario / OFX.

---

## Qué es un “split” de transacción

Un extracto bancario muestra **un solo cargo**. En el presupuesto a veces ese cargo debe repartirse en varias categorías.

Ejemplo: Éxito −$200.000

| Parte | Categoría | Monto |
|-------|-----------|------:|
| 1 | Mercado | $120.000 |
| 2 | Aseo | $50.000 |
| 3 | Cuidado personal | $30.000 |

El banco ve 1 movimiento; el presupuesto ve 3 asignaciones. Sin split se falsean datos o se “ensucia” una sola categoría.

Backend ya existe (`TransactionSplit` + `transaction_service`). Falta exponerlo en API schemas + UI.

---

## Fase 1 — Base diaria

**Objetivo:** cerrar huecos de uso diario y visibilidad inmediata.  
**Estado:** ✅ Aprobada

| # | Feature | Estado | Entregable |
|---|---------|--------|------------|
| 1.1 | Split de transacciones (UI + API) | ✅ | Schemas `splits` + editor en modal Transacciones + badge “Dividida” |
| 1.2 | Age of Money KPI | ✅ | Card en Dashboard vía `GET /reports/summary` |
| 1.3 | Gasto por comercio/payee | ✅ | `GET /reports/spending-by-payee` + tabla en Reportes |
| 1.4 | Comparativa mes vs mes | ✅ | `GET /reports/month-comparison` + tabla en Reportes |
| 1.5 | Feedback loop de reglas | ✅ | Confirm al categorizar tx con beneficiario → `merchantRules.create` |
| 1.6 | Centro de notificaciones | ✅ | Campana topbar fusiona `/alerts/budget` + `/alerts/smart-notifications` |

### Criterios de aceptación Fase 1

- [x] Se puede dividir un gasto en ≥2 categorías y el presupuesto refleja cada parte.
- [x] Dashboard muestra “Edad del dinero” en días.
- [x] Reportes muestra top comercios del mes.
- [x] Reportes muestra comparación mes actual vs anterior por categoría.
- [x] Al cambiar categoría de una tx con comercio, se ofrece crear regla.
- [x] Icono de campana muestra alertas de presupuesto + smart notifications.

---

## Fase 2 — Control y proyección

**Estado:** ✅ Aprobada

| # | Feature | Estado | Entregable |
|---|---------|--------|------------|
| 2.1 | Aprobación de recurrentes | ✅ | Inbox Aprobar / Saltar / Posponer + `snoozed_until` |
| 2.2 | Lógica pago TC en presupuesto | ✅ | Cargo TC → crédito automático a categoría Pago TC |
| 2.3 | Proyección caja 30/60/90 | ✅ | Incluye cuotas diferidas; evita doble conteo vs mínimo TC |
| 2.4 | Bloqueo meses conciliados | ✅ | `locked` al cerrar sesión; no editar/borrar |
| 2.5 | Búsqueda global | ✅ | Barra topbar → cuentas/categorías/deudas/txs |
| 2.6 | Export CSV amplio | ✅ | Presupuesto, deudas, patrimonio, reportes |

### Criterios de aceptación Fase 2

- [x] En Recurrentes aparece inbox con Aprobar / Saltar / Posponer.
- [x] Un gasto en tarjeta con categoría de pago vinculada aumenta disponible en “Pago TC”.
- [x] Flujo de caja incluye cuotas (`source: installment`).
- [x] Tras finalizar reconciliación, txs cleared quedan bloqueadas.
- [x] Búsqueda en topbar encuentra entidades y navega.
- [x] Botones Exportar en presupuesto, deudas, patrimonio y reportes.

---

## Fase 3 — Metas y “qué pasa si”

**Estado:** ✅ Implementada — esperando aprobación

| # | Feature | Estado | Entregable |
|---|---------|--------|------------|
| 3.1 | Tipos de meta completos | ✅ | `target_balance_by_date` / `needed_for_spending` / `monthly_builder` + UI |
| 3.2 | Ritmo vs meta en dashboard | ✅ | Card “Necesitas $X/mes” + badge Al día / Atrasada |
| 3.3 | Sinking funds / sobres | ✅ | Meta + fecha en categoría; barra de progreso en presupuesto |
| 3.4 | Simulador combinado | ✅ | `/what-if` — un dial → deuda + emergencia + FIRE |
| 3.5 | Alertas de tendencia | ✅ | Campana: `trend_warning` (+N% vs promedio) vía smart notifications |
| 3.6 | Snapshots automáticos patrimonio | ✅ | Upsert al arranque + chart en Patrimonio |

### Criterios de aceptación Fase 3

- [x] Se puede crear meta con los 3 tipos (incl. ahorro mensual fijo).
- [x] Dashboard muestra ritmo (“necesitas $X/mes”) y alerta si va atrasada.
- [x] En presupuesto, categoría con monto meta muestra badge “Sobre” y barra de progreso.
- [x] `/what-if` proyecta impacto de un extra mensual en deudas, emergencia y FIRE.
- [x] Campana muestra alertas de tendencia por categoría (si hay gasto anómalo).
- [x] Patrimonio muestra gráfico de evolución neta (snapshot del mes actual al abrir).

### Archivos tocados Fase 3

**Backend**
- `models/goal.py`, `models/category.py` — `goal_type`, `monthly_amount`, `target_date`
- `database.py` — migraciones columnas
- `services/goal_service.py`, `goal_budget_service.py`
- `services/whatif_service.py`, `api/whatif.py`
- `api/goals.py`, `api/categories.py`
- `api/reports_pkg/net_worth.py` + upsert en `app.py` lifespan
- `services/smart_notifications_service.py` — tendencias (ya existía)

**Frontend**
- `static/js/pages/goals.js` — tipos de meta + ritmo en cards
- `static/js/pages/dashboard.js` — card ritmo de metas
- `static/js/pages/budget.js` — sinking fund en fila + modal
- `static/js/pages/what-if.js` + ruta/sidebar
- `static/js/pages/patrimonio.js` — timeline patrimonio neto
- `static/js/api/client.js` — `whatIf`, `netWorthTimeline`

### Cómo probar Fase 3

1. **Metas:** `/goals` → Nueva → elegir tipo (p. ej. “Ahorro mensual fijo”) → crear → ver badge y “Necesitas $X/mes”.
2. **Dashboard:** card “Ritmo de metas” con Al día / Atrasada.
3. **Sobre:** Presupuesto → Editar categoría → monto meta + fecha → fila muestra badge “Sobre” y barra.
4. **Qué pasa si:** sidebar → dial de extra → cambia meses de deuda / cobertura / años FIRE.
5. **Tendencias:** campana topbar (si hay categoría con gasto ≫ promedio).
6. **Patrimonio:** gráfico “Evolución patrimonio neto” (al menos el mes actual).

---

## Fase 4 — Inversiones / FIRE

**Estado:** ⏳ Pendiente (arranque tras `aprobado fase 3`)

| # | Feature | Entregable |
|---|---------|------------|
| 4.1 | Dividendos y DRIP | Registro + proyección ingreso pasivo |
| 4.2 | Rebalanceo con alertas | Drift vs target + sugerencia |
| 4.3 | Benchmarks | Portafolio vs índice / inflación CO |
| 4.4 | Aporte programado a inversión | Recurrente hacia activo/portafolio |
| 4.5 | Ganancias capital / lotes FIFO | Base fiscal al vender |

---

## Fase 5 — Producto y operación

**Estado:** ⏳ Pendiente

| # | Feature | Entregable |
|---|---------|------------|
| 5.1 | Undo / historial de cambios | Auditoría reversible de ediciones |
| 5.2 | Adjuntos de comprobantes | PDF/foto en transacción |
| 5.3 | Calendario de vencimientos | TC, hipoteca, seguros, suscripciones |
| 5.4 | Detección de suscripciones | Patrones recurrentes no declarados |
| 5.5 | Matching de reembolsos | Vincular cargo + devolución |
| 5.6 | PWA / móvil usable | Instalable y usable en teléfono |
| 5.7 | Onboarding DB nueva | Guía primera cuenta → plantilla → categorías |
| 5.8 | Auth condicional | `AUTH_ENABLED` si hay deploy remoto |

---

## Fase 6 — Nice-to-have

**Estado:** ⏳ Pendiente

| # | Feature | Entregable |
|---|---------|------------|
| 6.1 | Gastos compartidos / IOUs | “Pagué yo, me deben” |
| 6.2 | Impuestos Colombia | Deducibles + resumen anual |
| 6.3 | Seguros y renovaciones | Pólizas, primas, fechas |
| 6.4 | Ajuste por inflación | Metas/FIRE en pesos reales |
| 6.5 | Multi-usuario / hogar | Presupuestos compartidos |

---

## Cómo aprobar una fase

Al cerrar una fase, el agente reporta:

1. Checklist de aceptación (marcado).
2. Archivos tocados.
3. Cómo probar en UI.

Respuesta esperada del usuario:

- `aprobado fase N` → se inicia N+1  
- `ajustes: …` → se corrige sin avanzar  
- `pausar` → se detiene el roadmap

---

## Historial de avance

| Fecha | Evento |
|-------|--------|
| 2026-08-12 | Documento creado. Inicio Fase 1. |
| 2026-08-12 | Fase 1 implementada. Esperando aprobación. |
| 2026-08-12 | Fase 1 aprobada. Fase 2 implementada. Esperando aprobación. |
| 2026-08-12 | Fase 2 aprobada. Fase 3 implementada. Esperando aprobación. |
