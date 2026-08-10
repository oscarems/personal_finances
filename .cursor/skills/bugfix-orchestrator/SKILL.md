---
name: bugfix-orchestrator
description: Orquesta la corrección de bugs del catálogo docs/BUGS_AUDIT_2026-08.md usando agentes bugfix-* en olas paralelas con dominios disjuntos. Usar cuando el usuario pida corregir bugs de la auditoría, lanzar ola A/B/C, o el sistema de agentes bugfix.
---

# Bugfix orchestrator

## Fuente de verdad

1. Lee `docs/BUGS_AUDIT_2026-08.md` (IDs, severidad, agente, estado).
2. Lee el prompt del agente en `.cursor/agents/bugfix-<nombre>.md` (o `.claude/agents/`).
3. Tras cada ola, actualiza estados en el catálogo y corre verificación.

## Olas (paralelo dentro de la ola)

| Ola | Agentes (dominios disjuntos) | IDs |
|-----|------------------------------|-----|
| A (P0) | `bugfix-cover` \|\| `bugfix-portfolio-fire` | BUG-001…007 |
| B (P1 BE) | `bugfix-debt-fx` \|\| `bugfix-budget-calc` | BUG-008…014, +023/024 |
| C (FE UX) | `bugfix-fe-ux` | BUG-015…022 |
| D | residuales de cada agente | BUG-025…032 |

**Nunca** lances dos agentes que editen el mismo archivo a la vez.

## Cómo lanzar

1. Marca los IDs de la ola como `in_progress` en el catálogo.
2. Lanza Task/subagentes en paralelo con el **system prompt completo** del `.md` del agente + “Implementa ahora los bugs de tu dominio; repo en `D:/Github/personal_finances`”.
3. Si el tipo `bugfix-*` no está en el enum de Task, usa `generalPurpose` / `shell` con ese prompt.
4. Espera reportes; resuelve conflictos de merge si los hay (no deberían: dominios disjuntos).
5. Corre tests relevantes y, si aplica, el agente `verifier`.
6. Marca IDs `fixed` + changelog; un commit por ola **solo si el usuario lo pide**.

## Gate verifier (bugfix)

```bash
python -m pytest tests/test_budget_service.py tests/test_transaction_service.py tests/test_fx_domain.py -q
```

Smoke FE (si app arriba):
- `GET /` spa
- Abrir hash/rutas `/portfolio` y `/fire` → no spinner eterno
- Presupuesto: cover move available (manual)

## Reportar al usuario

Resumen corto: IDs fixed / blocked / residual risk. No listar archivos irrelevantes.
