# Sistema multiagente y feedback loop del proyecto

Este documento describe cómo se organiza el desarrollo del proyecto usando subagentes de Claude Code y un ciclo de revisión continua. Complementa `docs/PROPUESTA_MEJORAS_2026-07.md`.

## Agentes definidos (`.claude/agents/`)

| Agente | Dominio | Cuándo usarlo |
|---|---|---|
| `fase1-backup` | Backups automáticos de SQLite + endpoint de descarga | Robustez técnica, sección 1.4 del plan |
| `fase1-tests` | Tests de `transaction_service.py` y `budget_service.py` | Cobertura de tests, sección 1.2 |
| `fase1-health-dashboard` | Semáforo de salud financiera en dashboard | UX, sección 2.4 |
| `backend-fixer` | Bugs de backend (rutas, SQLAlchemy legacy) | Ya usado en Fase 2 histórica |
| `design-system-builder` | Tema Nocturno y componentes compartidos | Ya usado en Fase 3, capa congelada |
| `page-migrator` | Migración de páginas al design system | Ya usado en Fase 4 |
| `ui-designer` / `ui-implementer` / `ui-reviewer` | Ciclo de diseño → implementación → revisión de UI | Features nuevas de UI |
| `janitor` | Limpieza de archivos legacy | Mantenimiento puntual |
| `verifier` | Chequeo post-fase: tests, rutas HTTP, recorrido del SPA | Cierre de cada fase |

**Patrón de trabajo:** cada fase del roadmap se divide en agentes con dominios de archivos disjuntos (backend puro / tests / una página frontend) para poder correrlos en paralelo sin conflictos de edición. Al terminar, el orquestador (la sesión principal de Claude) revisa el diff completo, corre `verifier`, y hace un solo commit por fase.

## Feedback loop de calidad

Después de cada fase de agentes:

1. **Verificación funcional** — invocar al agente `verifier` (o el skill `/verify`) contra los archivos tocados: tests, arranque de la app, recorrido de las rutas afectadas del SPA.
2. **Revisión de código** — correr `/code-review` (nivel `medium` para cambios de fase, `high` si toca lógica financiera sensible como amortización o presupuesto) sobre el diff antes de commitear.
3. **Commit único por fase** — solo tras pasar 1 y 2.
4. **Actualizar el roadmap** — marcar el ítem como hecho en `docs/PROPUESTA_MEJORAS_2026-07.md` y anotar cualquier hallazgo nuevo (bug descubierto, deuda técnica) como ítem futuro.

Para automatizar el ciclo de revisión continua sin intervención manual en cada paso, usar el skill `/loop`:

```
/loop 30m /code-review medium
```

Esto corre una revisión de código cada 30 minutos mientras haya cambios pendientes en el working tree — útil durante sesiones largas de trabajo con múltiples agentes en paralelo, para detectar regresiones temprano en vez de acumularlas hasta el final de la fase.

## Reglas para nuevos agentes de fase

Al crear un agente nuevo para una fase futura:
- Nombre: `faseN-<dominio>.md` (ej. `fase2-export-csv.md`).
- Frontmatter con `name` y `description` de una línea, mencionando la fase y sección del plan que cubre.
- Sección **Reglas absolutas**: qué archivos puede tocar (dominio disjunto de otros agentes de la misma fase) y que no debe commitear.
- Sección **Tareas**: instrucciones concretas con nombres de archivo y línea aproximada cuando se conozcan.
- Sección **Al terminar**: qué debe reportar al orquestador para poder verificar sin releer todo el diff.
