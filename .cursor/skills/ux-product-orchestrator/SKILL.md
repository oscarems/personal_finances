---
name: ux-product-orchestrator
description: Orquesta mejoras UX/producto del catálogo docs/UX_PRODUCT_AUDIT_2026-08.md con agentes ux-* y feat-* en olas paralelas de dominios disjuntos. Usar cuando el usuario pida sistema de agentes UX, ola A/B/C de UX, o implementar el análisis de gaps/UI.
---

# UX / Product orchestrator

## Fuente de verdad

1. `docs/UX_PRODUCT_AUDIT_2026-08.md`
2. Prompts en `.cursor/agents/ux-*.md`, `.cursor/agents/feat-due-calendar.md` (espejo `.claude/agents/`)
3. Tras cada ola: actualizar estados + `verifier` / smoke SPA

## Olas

| Ola | Paralelo | IDs |
|-----|----------|-----|
| A | `ux-nav-ia` \|\| `ux-dashboard-action` | UX-001…003 |
| B | `ux-page-states` \|\| `ux-mobile` | UX-004…005 |
| C | `feat-due-calendar` | UX-006 |
| D | backlog | UX-007…010 |

**Nunca** dos agentes editando el mismo archivo a la vez.  
Ojo: Ola C toca `app.js` — **no** solapar con Ola A (`ux-nav-ia` también toca `app.js`). Secuenciar A → B → C.

## Cómo lanzar

1. Marcar IDs `in_progress` en el catálogo.
2. Task `generalPurpose` (o tipo enum si existe) con el **system prompt completo** del `.md` + “Implementa ahora; repo `D:/Github/personal_finances`”.
3. Esperar reportes; resolver conflictos.
4. Smoke: `/`, `/budget`, `/transactions`, `/email-sender-rules`, `/calendar` (tras C).
5. Commit por ola **solo si el usuario lo pide**.

## Gate

```bash
python -m pytest tests/test_budget_service.py tests/test_transaction_service.py -q
```

SPA: sidebar grupos correctos; dashboard hero de acción; páginas débiles con Reintentar; mobile overflow.

## Reportar

IDs fixed / blocked / residual. Corto.
