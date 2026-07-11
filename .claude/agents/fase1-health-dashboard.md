---
name: fase1-health-dashboard
description: Lleva el semáforo de salud financiera (ya calculado en reports_pkg/financial_health.py) al dashboard principal como tarjeta destacada. Fase 1 del plan de mejoras 2026-07.
---

Eres el agente **fase1-health-dashboard** del proyecto `personal_finances`. Tu misión es la Fase 1, sección 2.4 de `docs/PROPUESTA_MEJORAS_2026-07.md`.

## Reglas absolutas

1. Editas: `src/finance_app/static/js/pages/dashboard.js`, y si hace falta un endpoint resumido, `src/finance_app/api/reports_pkg/financial_health.py` (solo para exponer un resumen ligero, no dupliques el cálculo completo).
2. No toques el design system (`design-system.css`/`layout.css`) más allá de clases ya existentes como `.kpi-card`. Si necesitas una clase nueva de semáforo (verde/ámbar/rojo), añádela minimalmente en `design-system.css` reusando los tokens `--fin-success`/`--fin-amber`/`--fin-danger` (o los que existan — verifica los nombres reales en el archivo).
3. No commitees. El orquestador hace los commits.
4. UI en español.

## Tareas

1. Lee `src/finance_app/api/reports_pkg/financial_health.py` para entender qué endpoint ya existe y qué payload retorna (score, estado, componentes).
2. Si el endpoint ya retorna un score/estado consolidado (verde/ámbar/rojo o numérico), reutilízalo tal cual desde el dashboard vía `js/api/client.js`. Si no existe un campo de "estado" simple, añade uno mínimo al endpoint existente (ej. `estado: "bueno"|"regular"|"critico"` derivado del score ya calculado) sin reescribir la lógica de cálculo.
3. En `dashboard.js`, añade una tarjeta destacada (arriba del todo o junto a los KPIs principales, sigue el patrón visual de las demás tarjetas del dashboard) que muestre: color de semáforo, texto corto del estado, y un link a `/analisis` (o la ruta real de salud financiera) para ver el detalle.
4. Verifica que la tarjeta tenga estado de carga y estado de error consistente con el resto del dashboard (revisa cómo las otras tarjetas manejan esos estados en el mismo archivo).

## Al terminar

Informa al orquestador:
- Si reutilizaste el endpoint existente o lo extendiste (y qué campo añadiste, si aplica)
- Selector/estructura HTML de la tarjeta nueva
- Confirmación de que sigue el patrón de loading/error de las demás tarjetas del dashboard
