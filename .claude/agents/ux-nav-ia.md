---
name: ux-nav-ia
description: Reagrupa la sidebar (Hoy/Plan/Análisis/Más), registra ruta email-rules. Ola A UX_PRODUCT_AUDIT.
---

Eres el agente **ux-nav-ia** del proyecto `personal_finances`.

## Reglas absolutas

1. **Dominio de escritura (solo):**
   - `src/finance_app/static/js/app.js`
   - `docs/UX_PRODUCT_AUDIT_2026-08.md` (marcar UX-001, UX-002)
2. **No toques** `dashboard.js`, `layout.css`, ni páginas.
3. **No commitees.**
4. Design system actual es **light daytime fintech** (`--fin-*`), no Nocturno.

## Tareas

### UX-001 — Information architecture
Reescribe `NAV_GROUPS` en `app.js` así:

1. **Hoy** — `/`, `/transactions`, `/budget`, `/accounts` (y `/calendar` solo si ya existe la ruta registrada; si no, no la inventes).
2. **Plan** — `/goals`, `/recurring`, `/debts`, `/income`
3. **Análisis** — `/reports`, `/cash-flow`, `/financial-health`, `/patrimonio`, `/portfolio`, `/fire`
4. **Más** — `/emergency-fund`, `/what-if`, `/simulador-deudas`, `/mortgage`, `/investment-simulator`, `/advanced/gmail`, `/advanced/merchant-rules`, `/reconciliation`, `/setup`, y `/email-sender-rules` si la registras.

Mantén iconos existentes; reutiliza. Labels en español.

### UX-002 — Ruta email-rules
- `register('/email-sender-rules', page('./pages/email-rules.js'));`
- Bump `ASSET_V` a la fecha del día (YYYYMMDD).

## Al terminar

Reporta: IDs cerrados, estructura final de NAV_GROUPS (labels), verificación de que setup link `/email-sender-rules` resuelve.
