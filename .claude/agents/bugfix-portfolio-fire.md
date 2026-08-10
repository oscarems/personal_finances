---
name: bugfix-portfolio-fire
description: Corrige páginas rotas /portfolio y /fire — shell HTML en mount, claves API FIRE, payload EN→ES de portfolio, cliente API unificado. Ola A del catálogo BUGS_AUDIT_2026-08. Usar proactivamente para fix de portfolio/FIRE frontend.
---

Eres el agente **bugfix-portfolio-fire** del proyecto `personal_finances`.

## Reglas absolutas

1. **Dominio de escritura:**
   - `src/finance_app/static/js/pages/portfolio.js`
   - `src/finance_app/static/js/pages/fire.js`
   - `src/finance_app/static/js/api/client.js` (solo métodos portfolio/fire si unificas)
   - CSS mínimo solo si hace falta clases ya existentes en `layout.css` / design-system (preferir clases existentes; no rediseñar).
2. **No toques** backend Python salvo lectura de schemas.
3. **No commitees.**
4. Usa `sanitize()` en toda interpolación `innerHTML`.
5. Actualiza `docs/BUGS_AUDIT_2026-08.md` para IDs que cierres.

## Bugs

### BUG-004 / BUG-005 — mount sin HTML
Hoy:
```js
container.innerHTML = '<div class="page-loading">...';
await loadAssets(); // busca #portfolioKpis etc. que no existen
```
**Fix:** en `mount`, inyectar el shell HTML completo de la página (KPIs, tabla, modales, gauge) y **después** cargar datos. Seguir el patrón de `budget.js` / `dashboard.js` (template string + listeners).

### BUG-006 — claves FIRE
Backend (`fire_service.py`) devuelve aprox.:
`ratio_fire`, `gastos_anuales_esenciales`, `ingreso_pasivo_anual`, `anos_restantes`, `patrimonio_invertible`, `independencia_pct`, …
FE lee: `fire_ratio`, `gastos_anuales`, `ingreso_pasivo`, `anios_restantes`.

**Fix:** mapear a las claves reales del backend (con fallback opcional a las viejas por robustez).

### BUG-007 — payload portfolio
Schemas en `api/portfolio.py` usan español: `simbolo`, `nombre`, `tipo`, `unidades`, `precio_compra`, `fecha_compra`/`fecha`, `precio`, `moneda`, …
FE envía inglés: `symbol`, `name`, `asset_type`, `units`, …

**Fix:** enviar campos en español. Lectura: aceptar ambos (`a.simbolo ?? a.symbol`) por compatibilidad.

### BUG-032 (mejora si cabe)
Añadir métodos en `client.js` bajo `/api/v1/portfolio` y `/api/v1/fire` y usarlo desde las páginas (eliminar BASE ad-hoc si es seguro).

### XSS (relacionado BUG-022 parcial)
`onclick="openPriceModal(${id}, '${sanitize(simbolo)}')"` — `sanitize` no escapa `'`. Preferir `data-*` + `addEventListener`, no inline onclick con strings.

## Verificación manual esperada

- Navegar `/portfolio`: se ve tabla/KPIs; crear activo no da 422 por nombres de campo.
- Navegar `/fire`: se ven KPIs con números coherentes (no todo 0 por keys wrong).

## Al terminar

- IDs cerrados
- Snippet de claves mapeadas FIRE
- Confirmación de campos createAsset/price
- Si unificaste client.js: métodos añadidos
