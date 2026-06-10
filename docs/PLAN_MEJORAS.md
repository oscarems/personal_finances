# Plan de Mejoras — Personal Finances

> **Documento de ejecución para un agente de coding.**
> Generado el 2026-06-10 a partir de una auditoría completa del código.
> Prioridades acordadas con el usuario: **(1) bugs y correctitud, (2) rediseño visual completo
> (tema oscuro fintech premium), (3) limpieza del repositorio.**
> El refactor profundo del backend NO está priorizado (ver Apéndice A).

---

## 0. Contexto y reglas de ejecución

### Qué es esta app

Gestor de finanzas personales local: FastAPI + SQLite (SQLAlchemy) en backend, SPA de
JavaScript vanilla (ES6 modules, sin bundler) en frontend. El backend sirve la API REST
bajo `/api/*` y hace fallback a `src/finance_app/static/index.html` para el routing
client-side (History API). Charts con Chart.js 4 (CDN).

- **Entry point:** `python run.py` (mata el proceso previo en el puerto y arranca uvicorn).
- **Tests:** `python -m pytest tests/ -q` desde la raíz del repo.
- **Código backend:** `src/finance_app/` (api/, services/, models/, domain/, config/).
- **Código frontend:** `src/finance_app/static/` (js/pages/, js/components/, js/api/, styles/, css/).
- **Existe el skill `run-app`** para lanzar la app y probarla en navegador — úsalo para verificar.

### Reglas globales (NO violar)

1. **Frontend vanilla:** nada de frameworks, bundlers ni dependencias npm. ES6 modules nativos.
2. **No modificar datos financieros** del usuario sin confirmación explícita. Las bases
   `.sqlite` en `data/` no se tocan.
3. **No agregar funcionalidades no solicitadas** en este plan.
4. **Sanitizar todo string de usuario** que se interpole en `innerHTML` con `sanitize()`
   de `static/js/utils.js`.
5. **Una fase = un commit (mínimo).** Mensajes descriptivos. No mezclar fases en un commit.
6. **Cada fase termina con su sección "Verificación" en verde** antes de pasar a la siguiente.
7. Auth queda **deshabilitada** (decisión del usuario: app solo local), pero debe quedar
   *coherente* (ver tarea 2.4), no a medias como ahora.
8. La app es bilingüe en código (dominio en español, técnico en inglés) — mantener esa convención.
   Toda la UI visible es en **español**.

### Estado actual verificado (baseline de la auditoría)

- `pytest`: **61 tests pasan**; `tests/test_module_changes.py` está **roto** (ImportError).
- **805 atributos `style="..."` inline** en `static/js/pages/*.js`.
- **34 `.catch(() => …)` silenciosos** (11 en `js/api/client.js`, 23 en páginas).
- `index.html` carga las fuentes **Fraunces y Figtree que nadie usa**, y NO carga **Inter**,
  que es la que `design-system.css` declara (`--fin-font: 'Inter'`). Hoy la UI se renderiza
  con la fuente del sistema sin que nadie lo haya decidido.
- Carpetas legacy sin referencias desde `src/`: `backend/`, `finance_app/` (raíz), `alembic/`.
- `src/finance_app/templates/`: solo se usan `login.html`, `chat_ui.html` y `base.html`
  (este último porque `chat_ui.html` lo extiende). El resto (~20 templates) es código muerto
  de la era server-rendered.

---

## Fase 0 — Baseline

Objetivo: dejar constancia del estado inicial para poder comparar.

1. Crear rama de trabajo: `git checkout -b mejoras/plan-2026-06`.
   *Nota: hay muchos archivos modificados sin commitear en `main`. Si el working tree no está
   limpio, commitea primero el estado actual en `main` con mensaje `WIP antes de plan de mejoras`
   (preguntar al usuario solo si hay conflicto real).*
2. Ejecutar `python -m pytest tests/ -q` y guardar el resultado en la descripción del primer commit.
3. Lanzar la app (`run-app` skill o `python run.py`) y verificar que el dashboard carga en
   `http://localhost:8000`.

**Verificación:** la app arranca, dashboard renderiza, 61 tests pasan (1 módulo con ImportError conocido).

---

## Fase 1 — Limpieza del repositorio

Objetivo: eliminar código muerto y artefactos. **Antes de borrar cada ítem, ejecutar el grep
de verificación indicado**; si aparece alguna referencia desde código vivo (`src/`, `run.py`,
`tests/`), NO borrar y reportarlo.

### 1.1 Carpetas legacy

| Ítem | Verificación previa | Acción |
|---|---|---|
| `backend/` (raíz) | `grep -rn "from backend\|import backend" src/ tests/ run.py` → debe estar vacío (ya verificado) | Borrar carpeta |
| `finance_app/` (raíz, solo contiene `__pycache__`) | Confirmar que solo hay `__pycache__` dentro | Borrar carpeta |
| `alembic/` | `grep -rn "alembic" src/ run.py tests/` → vacío (solo aparece en requirements.txt) | Borrar carpeta; quitar `alembic` de `requirements.txt`. Las migraciones reales viven en `database.py::_apply_sqlite_migrations()` |
| `src/finance_app/templates/*` excepto `login.html`, `chat_ui.html`, `base.html` | `grep -rn "TemplateResponse\|templates/" src/finance_app --include="*.py"` — solo `auth.py` y `api/chat.py` usan templates | Borrar los demás `.html` (accounts, budget, debts, mortgage, reports/, patrimonio/, etc.). Revisar si `base.html` referencia css/js muertos y limpiarlo |

### 1.2 Archivos sueltos en la raíz

| Archivo | Acción |
|---|---|
| `sql.py` | Revisar contenido; si es script de pruebas ad-hoc, borrar |
| `test_olla.py` | Script de prueba de Ollama suelto — borrar (la lógica real está en `services/gmail_ollama_service.py`) |
| `compras.csv` | Dato personal de prueba — borrar del repo (si está trackeado, `git rm --cached` y añadir a `.gitignore`) |
| `app.log` | Borrar y añadir `*.log` a `.gitignore` |
| `web_scrapping_email.py` | **NO borrar** — es el parser de correos documentado en CLAUDE.md |
| `Funciones.md`, `docs/*` | **NO borrar** — documentación |

### 1.3 Higiene de git

1. Verificar que no haya `__pycache__/` ni `venv/` trackeados: `git ls-files | grep -E "__pycache__|^venv/"`.
   Si los hay: `git rm -r --cached <ruta>`.
2. Confirmar que `.gitignore` cubre: `__pycache__/`, `venv/`, `*.log`, `data/*.sqlite*`, `.env`.

### 1.4 Actualizar CLAUDE.md

La sección "Arquitectura de Carpetas" de `CLAUDE.md` describe una estructura
(`gestor_finanzas_personales/backend/...`, `frontend/...`) **que no corresponde al repo real**.
Reescribir esa sección con la estructura verdadera:

```
personal_finances/
├── run.py                      # Entry point (uvicorn)
├── web_scrapping_email.py      # Parser IMAP Gmail
├── src/finance_app/
│   ├── app.py                  # FastAPI app + routers
│   ├── auth.py                 # Login por cookie (deshabilitado, app local)
│   ├── database.py             # Engine, sesiones, migraciones (_apply_sqlite_migrations)
│   ├── api/                    # Routers (delgados)
│   ├── services/               # Lógica de negocio
│   ├── models/                 # SQLAlchemy models
│   ├── domain/                 # Lógica de dominio (debts, fx)
│   ├── config/                 # Settings
│   ├── templates/              # Solo login.html, chat_ui.html, base.html
│   └── static/                 # SPA: index.html, js/, styles/, css/
├── tests/
└── docs/
```

Eliminar también de CLAUDE.md las referencias a Alembic en la carpeta `db/` y cualquier
mención a la estructura `frontend/` inexistente.

**Verificación Fase 1:**
- `python -m pytest tests/ -q` → mismos resultados que el baseline.
- La app arranca y el dashboard, el chat (`/api/chat` UI si aplica) y `/login` siguen respondiendo.
- `git status` limpio tras el commit.

---

## Fase 2 — Bugs y correctitud

Cada tarea indica archivo:línea (números de la auditoría; pueden moverse ±5 líneas), el
problema, el fix y cómo verificarlo.

### 2.1 Ruta `GET /debts/timeline` inalcanzable (bug confirmado)

- **Dónde:** `src/finance_app/api/debts.py` — `@router.get("/{debt_id}")` está en la línea
  ~352 y `@router.get("/timeline")` en la ~561.
- **Problema:** FastAPI resuelve rutas en orden de registro. `/debts/timeline` matchea
  primero `/{debt_id}`, intenta parsear `"timeline"` como `int` y devuelve **422**. El
  frontend lo enmascara: `client.js` línea ~99 hace `.catch(() => [])`, así que la línea de
  tiempo de deudas simplemente nunca se muestra y nadie lo nota.
- **Fix:** mover el bloque completo de `get_debt_timeline` (junto con sus helpers `_parse_month`
  y `_iter_months` si solo los usa él) **antes** de la definición de `GET /{debt_id}`. Regla
  general: en cada router, todas las rutas literales (`/summary`, `/timeline`, `/simulator`,
  `/strategy-comparison`) van antes que las paramétricas (`/{debt_id}`).
- **Verificar:** con la app corriendo, `curl http://localhost:8000/api/debts/timeline` devuelve
  200 con JSON (no 422). Revisar también los demás routers por el mismo patrón — en la
  auditoría se revisaron `categories`, `accounts`, `goals`, `transactions`, `budgets`,
  `patrimonio`, `portfolio` y están bien; solo `debts.py` tiene el bug.

### 2.2 Test suite rota: `tests/test_module_changes.py`

- **Problema:** importa `calculate_available` de `budget_service`, función que ya no existe
  (el cálculo vive ahora en `recalculate_budget_available`, línea ~338). El módulo entero
  no se colecta y oculta cualquier regresión de lo que cubría.
- **Fix:** abrir el test, identificar qué comportamiento cubría cada caso y reescribir los
  imports/llamadas contra la API actual de `budget_service`. Si algún test cubre una función
  realmente eliminada sin reemplazo, borrar ese test con justificación en el commit.
- **Verificar:** `python -m pytest tests/ -q` colecta y pasa **todos** los módulos (0 errores
  de colección).

### 2.3 Errores silenciados en el frontend (política de errores)

- **Problema:** hay 34 `.catch(() => valorPorDefecto)`. Dos casos especialmente graves para
  una app financiera:
  - `static/js/pages/dashboard.js:16` → `api.exchangeRates.current().catch(() => ({ rate: 4200 }))`:
    si el endpoint falla, **el patrimonio neto se calcula con una tasa de cambio inventada
    (4200) sin avisar al usuario**.
  - `static/js/api/client.js:200` → `current: () => get('/exchange-rates/current').catch(() => ({ USD: 1, COP: 1 }))`:
    además el shape del fallback ni siquiera coincide con lo que espera el dashboard (`fxData?.rate`).
- **Fix (política a aplicar en todo el frontend):**
  1. **`js/api/client.js` nunca traga errores.** Eliminar los 11 `.catch()` del client; el
     client solo lanza. (Buscar: `grep -n "catch" src/finance_app/static/js/api/client.js`.)
  2. En las páginas, para datos **secundarios/opcionales** (alerts, goals, patrimonio en
     dashboard), está permitido degradar, pero con un helper explícito. Añadir a `utils.js`:
     ```js
     // Degrada a `fallback` si la promesa falla, registrando y notificando una sola vez.
     export async function optional(promise, fallback, label) {
       try { return await promise; }
       catch (err) {
         console.error(`[${label}]`, err);
         notifyDegraded(label); // toast "Algunos datos no cargaron: {label}" — agrupado, no spam
         return fallback;
       }
     }
     ```
     Implementar `notifyDegraded` con deduplicación (un solo toast por carga de página que
     liste los módulos caídos).
  3. Para datos **primarios** (tasa de cambio, cuentas, transacciones, presupuesto): si fallan,
     la página muestra su estado de error (`alert alert-danger`) — nunca un número inventado.
     En el dashboard concretamente: si `/exchange-rates/current` falla, mostrar el banner
     "No se pudo obtener la tasa de cambio — los totales consolidados están ocultos" y omitir
     las cards consolidadas en COP, en vez de usar 4200.
  4. Reemplazar los 23 `.catch(() => …)` de las páginas por `optional(...)` o por manejo de
     error visible, según sea dato secundario o primario.
- **Verificar:** apagar el backend a medias es difícil; en su lugar, en DevTools bloquear
  la request a `/api/exchange-rates/current` (Network request blocking) y recargar el
  dashboard → debe aparecer el banner y NO un patrimonio calculado con 4200.

### 2.4 Coherencia de auth (queda deshabilitada, pero bien)

- **Problema:** `auth.py::_valid_session` retorna siempre `True` (auth deshabilitada a
  propósito), pero `app.py:64` **exige `APP_PASSWORD`** al arrancar y lanza `RuntimeError`
  si no está. Mitad y mitad: pides una contraseña que luego no se usa.
- **Fix (app local, decisión del usuario):**
  1. En `app.py`, eliminar el bloque del lifespan que lanza `RuntimeError` si falta `APP_PASSWORD`.
  2. En `auth.py`, dejar `_valid_session` retornando `True` pero documentar en el docstring
     del módulo: *"Auth deshabilitada deliberadamente — app de uso local. Para rehabilitarla,
     restaurar la verificación de cookie firmada en `_valid_session` (ver git history,
     commit 1480f54)."*
  3. Quitar el link/flujo de login de la UI si existe alguno visible.
- **Verificar:** la app arranca sin `APP_PASSWORD` definida.

### 2.5 Auditoría de `sanitize()` en interpolaciones

- **Problema:** 23 de 24 páginas importan `sanitize`, pero no se auditó campo por campo.
  Datos que vienen de correos de Gmail (`lugar_transaccion`, descripciones) entran a
  `innerHTML`.
- **Fix:** revisar cada página (prioridad: `gmail-import.js`, `transactions.js`, `chat.js`,
  que renderizan texto externo) y envolver con `sanitize()` toda interpolación de:
  descripción, payee/lugar, nombres de cuenta/categoría/meta, mensajes de error, y cualquier
  campo de email. Identificar la página que NO importa `sanitize` y corregirla.
- **Verificar:** crear una transacción manual con descripción `<img src=x onerror=alert(1)>`
  y confirmar que se muestra como texto literal en transacciones, dashboard y reportes.
  Borrarla después.

### 2.6 Warnings de SQLAlchemy 2.0 (solo los triviales)

- **Problema:** 146 warnings `Query.get()` legacy + `declarative_base()` deprecado
  (`database.py:145`).
- **Fix mínimo (no refactor):** reemplazo mecánico `db.query(Model).get(id)` →
  `db.get(Model, id)` en todo `src/`, y `declarative_base()` →
  `sqlalchemy.orm.declarative_base`. No tocar nada más del ORM.
- **Verificar:** `python -m pytest tests/ -q` pasa y el conteo de warnings baja drásticamente.

**Verificación Fase 2 (completa):**
- Todos los tests pasan, 0 errores de colección.
- `curl /api/debts/timeline` → 200.
- App arranca sin `APP_PASSWORD`.
- Dashboard con `/exchange-rates/current` bloqueado muestra banner, no datos inventados.
- Commit por cada tarea (2.1–2.6) o un commit por subgrupo coherente.

---

## Fase 3 — Design system oscuro "Nocturno" (rediseño visual completo)

Decisión del usuario: **tema oscuro fintech premium** (azul pizarra, estilo Linear /
Copilot Money). Un solo tema — **no** implementar toggle claro/oscuro (restricción de CLAUDE.md).

### 3.1 Estrategia

`design-system.css` ya centraliza tokens (`--fin-*` y aliases `--color-*`, `--bg-*`,
`--text-*`, etc.) y las páginas consumen mayormente los aliases. **La táctica es reemplazar
los VALORES de los tokens manteniendo los NOMBRES**, de modo que el 80% de la UI cambie de
tema sin tocar páginas. Lo que quede mal (estilos inline con colores hardcodeados, `rgba`
claros, etc.) se corrige en la Fase 4 página por página.

### 3.2 Nueva paleta — reemplazar el bloque `:root` de `design-system.css`

```css
:root {
  /* — Canonical — */
  --fin-bg:           #0F172A;   /* fondo app — azul noche */
  --fin-surface:      #1E293B;   /* cards */
  --fin-surface-2:    #16213A;   /* sunken: inputs, table heads, sidebar */
  --fin-ink:          #F1F5F9;   /* texto principal */
  --fin-ink-2:        #94A3B8;   /* texto secundario */
  --fin-ink-3:        #64748B;   /* texto soft/labels */
  --fin-accent:       #60A5FA;   /* azul — acciones, links, focus */
  --fin-accent-light: rgba(96, 165, 250, 0.15);
  --fin-success:      #34D399;   /* verde — positivo */
  --fin-danger:       #F87171;   /* rojo — negativo */
  --fin-danger-light: rgba(248, 113, 113, 0.12);
  --fin-amber:        #FBBF24;   /* warning */
  --fin-amber-light:  rgba(251, 191, 36, 0.12);
  --fin-border:       rgba(148, 163, 184, 0.14);
  --fin-radius:       14px;      /* antes 18px — más contenido, menos "blob" */
  --fin-font:         'Inter', system-ui, sans-serif;
  --fin-mono:         'JetBrains Mono', monospace;
}
```

Reglas de mapeo para el resto del `:root` (el agente debe recorrer TODO el archivo):

| Grupo de tokens | Regla |
|---|---|
| `--color-primary*` | Azul `#60A5FA`, hover `#3B82F6`, active `#2563EB`. `primary-50/100` → rgba azul 0.10/0.18 |
| `--color-success*` | `#34D399` / `#10B981` / `#059669` — **separar de primary** (hoy success == accent verde; en el tema nuevo primario=azul, éxito=verde) |
| `--color-danger*` | `#F87171` / `#EF4444` / `#DC2626` |
| `--color-warning*` / `--color-accent*` | `#FBBF24` / `#F59E0B` / `#D97706` |
| `--bg-surface-alt` | `#243049` |
| Sombras | En oscuro las sombras casi no se ven: usar `--shadow-soft: 0 1px 2px rgba(0,0,0,0.4)`, `--shadow-medium: 0 4px 16px rgba(0,0,0,0.45)`, `--shadow-strong: 0 12px 40px rgba(0,0,0,0.6)`. La elevación se comunica con **borde + fondo más claro**, no solo sombra |
| `--focus-ring` | `0 0 0 3px rgba(96, 165, 250, 0.35)` |
| Badges/alerts | Fondo rgba del color al 0.12, borde al 0.25, texto en la variante clara del color (p.ej. texto success `#6EE7B7`) — verificar contraste |
| `--radius-button`/`--radius-pill` | Botones: bajar de `100px` (píldora) a `10px` (rectangular suave, más fintech). Pills/badges sí mantienen `100px` |
| Tablas | head bg `--fin-surface-2`, row-hover `rgba(96,165,250,0.06)`, border `rgba(148,163,184,0.10)` |

### 3.3 Tipografía

1. En `static/index.html`, reemplazar la línea de Google Fonts: quitar **Fraunces** y
   **Figtree** (cargadas y jamás usadas), cargar **Inter** (400, 500, 600, 700) y mantener
   **JetBrains Mono** (400, 500).
2. Escala tipográfica (añadir tokens si no existen): `--text-xs: 0.72rem`, `--text-sm: 0.82rem`,
   `--text-base: 0.92rem`, `--text-lg: 1.1rem`, `--text-xl: 1.45rem`, `--text-2xl: 1.9rem`.
3. **Todos los montos en mono:** clase `.amount { font-family: var(--fin-mono); font-variant-numeric: tabular-nums; }`
   — se aplicará en Fase 4.
4. KPI values: `--text-2xl`, peso 600, mono, `letter-spacing: -0.02em`.

### 3.4 Chart.js — `static/js/chart-defaults.js`

Actualizar los defaults globales para el tema oscuro:

```js
Chart.defaults.color = '#94A3B8';
Chart.defaults.borderColor = 'rgba(148, 163, 184, 0.12)';
Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
// Tooltips: fondo #1E293B, borde rgba(148,163,184,0.2), texto #F1F5F9
// Grid: rgba(148,163,184,0.08); sin línea de borde de eje
```

Definir y exportar (en window, como ya hace el archivo) una paleta categórica para datasets,
pensada para fondo oscuro: `['#60A5FA','#34D399','#FBBF24','#F87171','#A78BFA','#22D3EE','#FB923C','#F472B6']`.
En Fase 4, las páginas que definen colores de chart hardcodeados migran a esta paleta.

### 3.5 Layout (`css/layout.css`)

- **Sidebar:** fondo `#0B1222` (un paso más oscuro que el bg), borde derecho `--fin-border`.
  Ítem activo: fondo `rgba(96,165,250,0.12)`, texto `#F1F5F9`, indicador de 3px azul a la
  izquierda. Labels de grupo en `--fin-ink-3`, caps, 0.68rem.
- **Topbar:** fondo `rgba(15,23,42,0.85)` con `backdrop-filter: blur(8px)`, borde inferior `--fin-border`.
- **Scrollbars:** estilizar (`::-webkit-scrollbar` 10px, thumb `rgba(148,163,184,0.25)`).
- **Selection:** `::selection { background: rgba(96,165,250,0.35); }`.
- **Consolidar duplicación:** hay reglas de sidebar tanto en `design-system.css` (4 matches)
  como en `layout.css` (22). Dejar TODO el layout estructural en `layout.css` y solo tokens
  en `design-system.css`.
- Revisar `base.html` (usado por chat_ui/login) para que también cargue el tema oscuro y no
  quede una página blanca suelta.

### 3.6 Clases utilitarias nuevas (para matar inline styles en Fase 4)

Añadir al final de `design-system.css` una sección `/* ── Utilities ── */` con, como mínimo:

```
.text-success, .text-danger, .text-warning, .text-muted, .text-soft
.amount  (mono + tabular-nums)
.flex, .flex-col, .items-center, .justify-between, .gap-1..4 (4/8/12/16px)
.mt-0..4, .mb-0..4 (0/4/8/12/16px)
.w-full
.grid-2, .grid-3, .grid-4 (con colapso responsive a 1 col < 768px)
.kpi-sub-stack (columna de sub-líneas de KPI con gap 3px)
```

**Verificación Fase 3:**
- App arriba: TODAS las páginas se ven oscuras sin zonas blancas "flash" (revisar `body` y
  `html` background, y el estado de loading inicial de `index.html`).
- Ninguna página quedó ilegible (texto oscuro sobre fondo oscuro) — recorrer las 24 rutas
  del sidebar con el navegador y captura rápida de cada una.
- Charts legibles (labels, grid, tooltips).
- Contraste AA en texto principal y secundario (Inter #F1F5F9 y #94A3B8 sobre #0F172A pasan).

---

## Fase 4 — Migración página por página

Objetivo: eliminar los **805 estilos inline**, corregir colores hardcodeados incompatibles
con el tema oscuro, y unificar componentes. Orden por impacto de uso:

| # | Página | Archivo | Inline styles aprox. |
|---|---|---|---|
| 1 | Dashboard | `pages/dashboard.js` | 73 |
| 2 | Presupuesto | `pages/budget.js` | 54 |
| 3 | Transacciones | `pages/transactions.js` | ~30 |
| 4 | Deudas | `pages/debts.js` | 35 |
| 5 | Reportes | `pages/reports.js` | 43 |
| 6 | Ingresos | `pages/income.js` | 53 |
| 7 | Salud Financiera | `pages/financial-health.js` | **125** |
| 8 | Importar Gmail | `pages/gmail-import.js` | **103** |
| 9 | Cuentas | `pages/accounts.js` | ~20 |
| 10 | Hipoteca, Simulador Deudas, Fondo Emergencia, Metas | varios | ~80 |
| 11 | Patrimonio, Portfolio, FIRE, Cash-flow | varios | ~60 |
| 12 | Recurrentes, Reconciliación, Reglas, Setup, Chat | varios | resto |

### 4.1 Procedimiento por página (repetir para cada una)

1. `grep -n 'style="' src/finance_app/static/js/pages/<página>.js` y clasificar cada caso:
   - **Layout repetido** (flex, gaps, márgenes) → utility class de 3.6.
   - **Color hardcodeado** (`color:var(--color-success)`, hex, rgba claros) → clase semántica
     (`.text-success`, `.badge-*`) o token. **Ningún hex/rgba de color en JS**, salvo paleta de charts.
   - **Patrón que se repite en ≥2 páginas** (sub-stack de KPI, fila label/valor, barra de
     progreso, empty state) → componente CSS con nombre en `design-system.css`.
   - **Único permitido inline:** valores dinámicos calculados (p.ej. `style="width:${pct}%"`
     en barras de progreso, `grid-template-columns` dinámico).
2. Aplicar la clase `.amount` a todo monto renderizado.
3. Verificar uso de `sanitize()` (cruce con tarea 2.5).
4. Estados obligatorios por página: **loading** (skeleton, ya existe el patrón en dashboard),
   **error** (alert con mensaje + botón "Reintentar" que vuelve a llamar `mount`), y
   **empty state** (icono + texto + acción primaria, p.ej. "No hay transacciones — + Agregar").
   Crear el helper `emptyState({ icon, title, hint, actionLabel, actionId })` en
   `js/components/` y usarlo en todas.
5. Charts de la página → paleta de 3.4, sin colores propios.
6. Probar la página en el navegador (con datos reales del usuario) antes de pasar a la siguiente.

### 4.2 Componentes compartidos a crear/unificar (detectados en la auditoría)

- **KPI card** (`.kpi-card` ya existe): estandarizar estructura
  `label → value(.amount) → sub(.kpi-sub-stack)`. Dashboard, income, debts, fire y
  financial-health la improvisan distinto cada uno.
- **Tabla financiera:** clase única `.fin-table` (head sticky opcional, columnas numéricas
  `.amount` alineadas a la derecha, hover row).
- **Progress bar:** ya hay `progressBar` en `utils.js` — unificar para que metas, presupuesto
  y deudas usen el mismo, con variantes de color por umbral.
- **Badge de moneda** (🇨🇴 COP / 🇺🇸 US): hoy se repite ad-hoc; extraer helper.
- **Modal y toast** ya existen en `js/components/` — solo asegurar estilos oscuros.

### 4.3 Detalles de diseño "premium" (aplicar durante la migración)

- Jerarquía del dashboard: patrimonio neto como héroe (card grande, valor 2xl), KPIs
  secundarios más pequeños; hoy las 3 cards compiten igual.
- Números negativos siempre `.text-danger` + signo; positivos `.text-success` solo cuando
  el contexto es delta/ganancia (no todo saldo positivo en verde — verde reservado a "bueno").
- Hover de cards: `transform: translateY(-1px)` + borde `--border-hover`; transición `--transition-fast`.
- Densidad: reducir paddings de cards de grandes a `20px`, tablas `10px 14px` — el tema
  oscuro premium es más denso que el "Arena" actual.

**Verificación Fase 4:**
- `grep -c 'style="' src/finance_app/static/js/pages/*.js` → solo quedan estilos dinámicos
  (objetivo: < 60 en total, todos con interpolación `${}`).
- Recorrido completo de las 24 rutas en navegador: sin glitches visuales, charts correctos,
  estados empty/error visibles donde aplique.
- `python -m pytest tests/ -q` sigue verde (el frontend no toca tests, pero confirma que no
  se rompió nada de backend por accidente).
- Un commit por página o por grupo de páginas pequeñas.

---

## Fase 5 — Pulido final y verificación de cierre

1. **Responsive:** probar a 390px (móvil), 768px y 1280px las páginas top-5. El sidebar móvil
   (overlay) ya existe — verificar que funciona con el tema nuevo.
2. **Accesibilidad mínima:** focus visible en botones/inputs/links (token `--focus-ring`),
   `aria-label` en botones de solo-icono (colapsar sidebar, menú móvil, cerrar modal).
3. **Title dinámico:** verificar que cada página setea el título del documento/topbar
   (`export const title` ya existe en las páginas — confirmar que el router lo aplica).
4. **Favicon** oscuro simple (opcional, 15 min máximo).
5. **Documentar:** actualizar `docs/DESIGN_SYSTEM.md` con la nueva paleta "Nocturno", la
   escala tipográfica, las utilities y las reglas de uso (cuándo verde/rojo, mono en montos,
   prohibición de estilos inline estáticos).
6. **Cierre:** correr `pytest`, recorrer las 24 rutas una última vez, y preparar un resumen
   de PR con: bugs corregidos (2.1–2.6), antes/después del conteo de inline styles, y
   capturas del dashboard.

---

## Apéndice A — Mejoras NO priorizadas (no ejecutar sin pedir confirmación)

Registradas en la auditoría; el usuario decidió no priorizarlas ahora:

1. **Refactor de servicios grandes:** `budget_service.py` (1161 líneas, mezcla queries,
   conversión de moneda y armado de respuesta) y `transaction_service.py` (1096 líneas,
   incluye lógica de impacto en deudas/hipoteca). División sugerida: `budget/` package
   (queries.py, currency.py, rollover.py, month.py) y extraer `debt_impact.py` de transactions.
2. **Routers gordos:** `api/debts.py` (926 líneas) tiene lógica de negocio en endpoints
   (`get_debts_summary` arma totales y alertas a mano; `create_debt_payment` ~60 líneas).
   Mover a `services/debt/`.
3. **Duplicación de conversión de moneda:** `_make_currency_converter` y
   `_make_currency_converter_2arg` en budget_service + lógica similar en
   `exchange_rate_service` — unificar en `domain/fx/`.
4. **Modernización completa SQLAlchemy 2.0** (estilo `select()`, `Mapped[]`).
5. **CORS `allow_origins=["*"]`** — irrelevante en local, restringir si algún día se despliega.
6. **Rehabilitar auth** — instrucciones en 2.4; solo si la app se expone a red.

## Apéndice B — Inventario de rutas SPA (para el recorrido de verificación)

`/` · `/accounts` · `/budget` · `/transactions` · `/income` · `/reports` · `/cash-flow` ·
`/financial-health` · `/patrimonio` · `/debts` · `/mortgage` · `/simulador-deudas` ·
`/goals` · `/emergency-fund` · `/investment-simulator` · `/recurring` · `/advanced/gmail` ·
`/advanced/merchant-rules` · `/portfolio` · `/fire` · `/reconciliation` · `/setup` ·
(`/login` y la UI de chat se sirven por templates Jinja).
