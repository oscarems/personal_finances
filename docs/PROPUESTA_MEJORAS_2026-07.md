# Propuesta de Mejoras — Julio 2026

Documento de diseño y roadmap priorizado. Cubre UX/diseño, robustez técnica y features nuevas, en partes iguales. No incluye implementación — es la base para decidir qué construir a continuación.

**Restricciones respetadas:** vanilla JS sin frameworks, sin dark-mode-toggle nuevo (ya existe Nocturno), sin Alembic (migraciones vía `_apply_sqlite_migrations`), app mono-usuario local, sin servicios externos de pago (todo lo propuesto usa librerías estándar / locales).

---

## 0. Panorama actual (resumen del audit)

- **24 módulos frontend**, **~28 routers**, **~25 servicios** — cobertura funcional ya es amplia: cuentas, presupuesto, transacciones, deudas/hipoteca, patrimonio, portafolio, FIRE, metas, alertas, notificaciones inteligentes, conciliación, recurrentes, importación Gmail (+ Ollama), chat.
- **Tests concentrados casi exclusivamente en deudas/amortización y patrimonio** (11 archivos). Budgets, accounts, transactions, gmail_import, chat, reconciliation, alerts, goals: sin cobertura.
- **Auth deshabilitada deliberadamente** (`auth.py`) — aceptable si la app es 100% local, pero hay `fly.toml`/`Dockerfile` que sugieren despliegue remoto: riesgo si se expone así.
- **Exportación de datos**: solo CSV de transacciones. Nada en reports, patrimonio, deudas, presupuesto.
- **`Funciones.md` fue borrado** del working tree (recuperable con `git show HEAD:Funciones.md`) — si documentaba funcionalidad, vale la pena decidir si se restaura o se reemplaza por este doc + README.

---

## 1. Robustez técnica

### 1.1 Seguridad — auth condicional al modo de despliegue (Alta prioridad si hay deploy remoto)
Actualmente `_valid_session()` siempre retorna `True`. Si la app solo corre en `localhost`, es aceptable. Pero existe `fly.toml`, lo que implica que en algún momento se pensó en exponerla en internet.

**Propuesta:** reactivar la verificación de cookie firmada, controlada por una variable de entorno `AUTH_ENABLED` (default `false` para uso local, `true` recomendado para despliegue). Cero fricción en local, protección real en remoto. No requiere modelo `User` (sigue siendo mono-usuario con `APP_PASSWORD`).

### 1.2 Cobertura de tests
Vacíos críticos: `budgets`, `accounts`, `transactions` (el módulo más usado a diario), `goals`, `alerts`, `reconciliation`.

**Propuesta de fases:**
1. `transaction_service.py` (creación, splits, transferencias, cálculo de disponible) — es el corazón de la app.
2. `budget_service.py` (cascade de meses futuros, `listo_para_asignar`, inicialización de mes).
3. Endpoints API con `TestClient` de FastAPI para accounts/goals/alerts (happy path + validación de errores).

### 1.3 Manejo de errores en frontend
Verificar (no confirmado en el audit) si `js/api/client.js` distingue errores de red vs errores 4xx/5xx vs validación, y si cada página muestra estado de error de forma consistente. Dado que hay 24 páginas independientes, un componente compartido `errorState` ya existente (ver Fase 3 en historial de commits) debería auditarse por consistencia de uso — candidato a pase rápido con el agente `ui-reviewer`.

### 1.4 Backups / integridad de datos
La app gestiona múltiples archivos `.sqlite` sin backup automático. Antes de una migración (`_apply_sqlite_migrations`) o de "eliminar base de datos", proponer:
- Copia automática `finanzas.sqlite.bak-YYYYMMDD` antes de aplicar migraciones nuevas.
- Botón "Exportar backup completo" en `/configuracion` (copia del archivo `.sqlite` activo, descarga directa — cero infraestructura nueva).

### 1.5 Documentación funcional
Restaurar o recrear `Funciones.md` — o formalizar que este archivo (`docs/PROPUESTA_MEJORAS_*.md`) y el `README.md` son la fuente de verdad, y así evitar duplicación divergente.

---

## 2. UX / Diseño

### 2.1 Exportación de datos (extender más allá de transacciones)
Hoy solo `transactions.py` exporta CSV. Usuarios de finanzas personales quieren llevarse sus datos.

**Propuesta (sin librerías de pago, usando `csv` estándar):**
- Export CSV en `reports_pkg` (spending por categoría, net worth timeline, financial health).
- Export CSV de deudas (tabla de amortización) y patrimonio.
- Un único componente JS reutilizable `exportButton` que llama a un endpoint `?format=csv` — patrón consistente en vez de un botón custom por página.

### 2.2 Búsqueda global
Con 24 páginas y potencialmente miles de transacciones, no hay (según el audit) una búsqueda unificada. Proponer una barra de búsqueda en el sidebar que busque en transacciones por descripción/lugar/monto y salte directo al resultado — patrón común en apps tipo YNAB/Firefly III.

### 2.3 Onboarding / vista vacía para bases de datos nuevas
`setup.py` existe, pero vale la pena revisar si al crear una base de datos nueva el usuario tiene una guía clara: crear primera cuenta → definir plantilla de presupuesto → categorías esenciales. Reduce fricción inicial, especialmente si el usuario cambia de base de datos (feature ya soportada) y quiere partir limpio.

### 2.4 Semáforo de salud financiera consolidado
Ya existe `financial_health.py`. Proponer llevar ese semáforo (o una versión resumida) al **dashboard principal** como tarjeta destacada: 1 vistazo → estado general (verde/ámbar/rojo) sin tener que navegar a `/analisis`.

### 2.5 Notificaciones — unificar los dos sistemas
Existen **dos sistemas paralelos**: `smart_notifications_service.py` (contextual, dashboard) y `alert_service.py` + `AlertRule`/`BudgetAlertState` (formal, con severidad/cooldown). Desde la perspectiva del usuario esto puede sentirse como dos bandejas distintas de avisos.

**Propuesta:** unificar la presentación en un solo "centro de notificaciones" (icono de campana en el header) que combine ambas fuentes, aunque el backend siga separado. Mejora de UX pura, sin tocar lógica de negocio.

### 2.6 Comparativa 50/30/20 y gasto esencial vs discrecional
Mencionado en el roadmap existente (Nivel 2) — reforzar aquí porque es alto valor/bajo esfuerzo: el campo `is_essential` en `Category` ya existe, solo falta el reporte y la vista de semáforo por categoría.

---

## 3. Features financieras nuevas

### 3.1 Presupuesto base cero — vista "Listo para Asignar" más prominente
`listo_para_asignar(db)` ya existe en el servicio de presupuesto. Popularizar esa cifra (método YNAB) en el header de `/presupuesto`, no solo en el dashboard, con feedback visual fuerte cuando quede dinero sin asignar.

### 3.2 Proyección de flujo de caja extendida
`cash_flow.py` ya existe. Proponer extenderlo con recurrentes conocidas (`recurring_transaction`) + cuotas de deuda (`debt_installment`) para proyectar saldo de cuentas a 30/60/90 días — responde la pregunta real del usuario: "¿me voy a quedar corto este mes?".

### 3.3 Reglas de categorización — feedback loop
`merchant_rule_engine.py` ya categoriza automáticamente. Proponer un flujo donde, si el usuario recategoriza manualmente una transacción de un merchant sin regla, la UI ofrezca "¿Crear regla para futuras transacciones de X?" con un solo clic — cierra el ciclo sin que el usuario tenga que ir a `/reglas`.

### 3.4 Importador CSV bancario (ya en roadmap Nivel 3)
Reforzado aquí: dado que ya existe exportación CSV de transacciones y `merchant_rule_engine.py`, el importador CSV puede reutilizar el mismo pipeline de deduplicación y categorización automática que usa `gmail_import.py`. Bajo esfuerzo incremental porque la infraestructura de parsing/matching ya existe.

### 3.5 Metas vinculadas a presupuesto — cálculo de "ritmo necesario"
`Goal`/`GoalContribution` y `goal_budget_service.py` ya existen. Verificar si ya calculan "necesitas ahorrar $X/mes para llegar a tiempo" (mencionado en roadmap Nivel 3) — si no, es la pieza que falta para que las metas sean accionables y no solo un tracker pasivo.

### 3.6 Simulador "qué pasa si" combinado
Hoy existen simuladores separados (deuda, fondo de emergencia, inversión, hipoteca). Proponer una vista combinada donde el usuario ajuste un solo parámetro (ej. "pago $500k extra/mes") y vea el impacto simultáneo en: tiempo para salir de deudas, meses de cobertura de emergencia, y años restantes para FIRE. Reutiliza los tres motores de cálculo existentes sin duplicar lógica — solo una vista de composición en frontend.

---

## 4. Roadmap priorizado

| Fase | Ítem | Esfuerzo | Justificación |
|---|---|---|---|
| **1** | Backup automático antes de migraciones + botón de export de `.sqlite` | Bajo | Protege contra pérdida de datos, cero UX nueva compleja |
| **1** | Tests de `transaction_service.py` y `budget_service.py` | Medio | Son el núcleo de la app y hoy no tienen cobertura |
| **1** | Semáforo de salud financiera en dashboard | Bajo | El cálculo ya existe, solo falta exponerlo |
| **2** | Export CSV extendido (reports, deudas, patrimonio) | Bajo-Medio | Patrón ya existe en transactions, se replica |
| **2** | Análisis esencial vs discrecional (50/30/20) | Bajo | Campo `is_essential` ya existe |
| **2** | Auth condicional (`AUTH_ENABLED`) | Bajo | Solo relevante si hay plan real de exponer la app |
| **3** | Centro de notificaciones unificado | Medio | Mejora de UX, requiere tocar 2 sistemas backend en el frontend |
| **3** | Proyección de flujo de caja extendida (recurrentes + cuotas) | Medio | Alto valor, requiere combinar 3 fuentes de datos |
| **3** | Feedback loop de reglas de categorización | Medio | Reduce fricción diaria de categorizar transacciones |
| **4** | Importador CSV bancario | Alto | Reutiliza pipeline existente pero requiere UI de revisión/rollback |
| **4** | Metas con cálculo de ritmo necesario (si no existe ya) | Medio | Requiere primero confirmar qué tiene `goal_budget_service.py` |
| **4** | Simulador combinado "qué pasa si" | Medio-Alto | Vista nueva, reutiliza motores existentes |
| **5** | Búsqueda global | Medio | Nice-to-have, no bloquea nada |
| **5** | Onboarding para bases de datos nuevas | Bajo-Medio | Mejora puntual, no crítica dado que el usuario ya conoce la app |

---

## 5. Preguntas abiertas para decidir alcance

1. ¿La app se va a desplegar remotamente en algún momento (justifica priorizar auth), o seguirá 100% local (baja prioridad)?
2. ¿`Funciones.md` tenía contenido que quieras recuperar de git history, o este documento + README lo reemplaza?
3. ¿Cuál de las fases 1–2 quieres atacar primero como próxima sesión de trabajo?
