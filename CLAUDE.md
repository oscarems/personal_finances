# Gestor de Finanzas Personales

Aplicación web local para organizar finanzas personales: cuentas, presupuesto, análisis de gastos, simuladores y registro automático de transacciones desde correos.

---

## Stack Tecnológico

| Capa         | Tecnología                         |
| ------------ | ---------------------------------- |
| Backend      | Python 3.12 + FastAPI              |
| Frontend     | HTML + JavaScript (vanilla ES6+)   |
| Base datos   | SQLite (via SQLAlchemy)            |
| Estilos      | CSS (custom, sin frameworks)       |
| Email        | IMAP Gmail (script existente)      |
| Tasas cambio | API externa (ej. exchangerate-api) |

La app corre completamente en local. El backend sirve la API REST y el frontend se sirve como SPA.

Módulos activos: cuentas, presupuesto, transacciones, análisis, simuladores, patrimonio, **portafolio de inversiones**, **dashboard FIRE**.

---

## Arquitectura de Carpetas

```
gestor_finanzas_personales/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── models/              # SQLAlchemy models
│   ├── routers/             # Endpoints por módulo
│   ├── services/            # Lógica de negocio
│   ├── schemas/             # Pydantic schemas
│   └── db/                  # Sesión y migraciones (Alembic)
├── frontend/
│   ├── index.html           # Punto de entrada
│   ├── css/
│   │   ├── main.css         # Estilos globales y variables
│   │   └── components/      # Estilos por componente
│   ├── js/
│   │   ├── pages/           # Lógica por página/sección
│   │   ├── components/      # Componentes reutilizables (funciones/módulos)
│   │   ├── api/             # Llamadas al backend (fetch wrappers)
│   │   └── utils/           # Helpers y utilidades
├── web_scrapping_email.py   # Script existente de parsing de correos
└── .env                     # Variables de entorno (no commitear)
```

---

## Módulos y Funcionalidades

### 1. Cuentas

Tipos de cuenta:

- **Ahorros**: saldo positivo, sin fecha de vencimiento.
- **Tarjeta de crédito**: tiene saldo de deuda (crece con compras, baja con pagos) + registro por compra individual. Requiere una categoría de presupuesto asociada al pago mensual.
- **Hipoteca**: requiere campo que indique si la cuota incluye seguros (sí/no). Requiere categoría de presupuesto asociada.
- **Préstamos**: monto original, tasa de interés, cuota mensual. Requiere categoría de presupuesto asociada.

Cada cuenta tiene:

- Nombre, tipo, moneda (COP o USD), saldo actual, institución financiera, notas opcionales.

Las deudas (tarjeta, hipoteca, préstamos) deben vincularse obligatoriamente a una categoría de presupuesto para su pago.

### 2. Presupuesto y Categorías

**Estructura del presupuesto:**

- Organizado por mes (YYYY-MM).
- Existe una **plantilla base** con los montos por defecto de cada categoría. Cada mes se inicializa desde esta plantilla, pero el usuario puede editar los montos mes a mes sin afectar la plantilla.

**Tipos de categoría:**

| Tipo   | Cálculo de "Disponible"                                     |
| ------ | ----------------------------------------------------------- |
| Gasto  | `disponible = asignado - gastado`                           |
| Ahorro | `disponible = disponible_mes_anterior + asignado - gastado` |

Cada categoría tiene: nombre, tipo (gasto/ahorro), grupo, ícono opcional.

Para cada mes y categoría, los valores son: `asignado`, `gastado`, `disponible` (calculado).

### 3. Transacciones

Una transacción válida requiere: **fecha, monto, cuenta, categoría**. Campos opcionales: descripción, lugar, moneda (si difiere de la cuenta).

**Método 1 — Manual**: El usuario ingresa la transacción desde la UI.

**Método 2 — Email**: El script `web_scrapping_email.py` (ya existente) lee el inbox de Gmail vía IMAP y extrae transacciones usando regex. El script exporta: `fecha`, `valor`, `moneda`, `cuenta`, `clase_movimiento`, `lugar_transaccion`. Al importar al gestor, el usuario debe asignar categoría a cada transacción importada (o el sistema puede sugerir una por lugar/comercio recurrente).

> Nota: el script actual usa regex, no Ollama. La integración con Ollama queda como mejora futura.

**Manejo de monedas múltiples:**

- Las cuentas tienen una moneda base (COP o USD).
- Las tasas de cambio COP/USD se consultan automáticamente via API externa y se cachean diariamente.
- Al mostrar totales consolidados, se usa la tasa del día de la transacción.

### 4. Análisis y Reportes

- Seguimiento de gastos filtrable por: día, semana, mes.
- Agrupación por categoría individual o grupo de categorías.
- Gráficos de tendencia mensual por categoría.
- Comparación mes actual vs mes anterior.
- Dashboard home con resumen: saldo total por cuenta, presupuesto del mes actual (gastado vs asignado), últimas transacciones.

### 5. Simulador de Fondo de Emergencia

- El usuario selecciona categorías de gasto (gastos mensuales esenciales) y categorías de ahorro (fondos disponibles).
- La UI calcula y muestra: `meses_cubiertos = total_ahorros / gasto_mensual_seleccionado`.
- Los gastos y ahorros se pueden ajustar en el simulador sin afectar los datos reales.

### 6. Simulador de Pago de Deuda

Para cada cuenta de tipo deuda:

- Mostrar saldo actual, tasa de interés, cuota mínima.
- Simular escenarios de pago anticipado:
  - **Abono a capital**: cuánto se ahorra en intereses y en tiempo.
  - **Método avalancha**: pagar primero la deuda con mayor tasa.
  - **Método bola de nieve**: pagar primero la deuda con menor saldo.
- Mostrar proyección de saldo en el tiempo (gráfico de amortización).
- **Comparador lado a lado**: tabla simultánea de avalancha vs. bola de nieve vs. solo mínimo (ruta `/simulador-deudas`).
- **Costo total**: interés pagado históricamente + proyección de "si solo pagas el mínimo".
- **Alertas de utilización**: banner automático cuando tarjeta supera 30% (warning) o 70% (critical).

### 7. Tarjetas de Crédito — Funcionalidades Específicas

- **Ciclo de facturación**: campos `statement_day` (día de corte) y `payment_due_day` (día límite), con cálculo automático de fecha de vencimiento del ciclo actual (`GET /debts/{id}/billing-cycle`).
- **Pago mínimo real**: campo `min_payment_percentage` (ej: 5%) usado en `calculate_suggested_minimum_payment`.
- **Tasa mensual efectiva**: campo `monthly_interest_rate` — si se define, el motor de amortización y todos los cálculos lo usan directamente en vez de derivar de la tasa anual.
- **Tipo de tasa**: campo `rate_type` (`fixed` / `variable`) para documentar si la tasa cambia.
- **Compras en cuotas** (`DebtInstallment`): modelo para diferidos, con cuotas totales/pagadas/restantes y resumen de saldo diferido pendiente. CRUD en `GET/POST/PATCH/DELETE /debts/{id}/installments`.

---

## Gestión de Bases de Datos

- Cada base de datos es un archivo `.sqlite` independiente.
- El usuario puede tener múltiples bases de datos y cambiar entre ellas desde la UI.
- **Eliminar una base de datos requiere doble confirmación explícita** (escribir el nombre de la base de datos).
- El programa nunca elimina datos sin confirmación del usuario.
- La base de datos activa se persiste en un archivo de configuración local (`config.json`).

---

## Diseño y UX

- Moderno, elegante, oscuro por defecto con opción de tema claro.
- Navegación lateral (sidebar) con acceso a cada sección.
- Cada módulo en su propia página/ruta.
- Paleta de colores: fondos oscuros (#0f172a, #1e293b), acentos en verde para positivo, rojo para negativo, azul para neutral.
- Tipografía limpia, números financieros en fuente monospace para alineación.

**Páginas principales:**

1. `/` — Dashboard / Home
2. `/cuentas` — Listado y detalle de cuentas
3. `/presupuesto` — Vista mensual del presupuesto
4. `/transacciones` — Registro y listado de transacciones
5. `/analisis` — Reportes y gráficos
6. `/simuladores` — Fondo de emergencia y pago de deudas
7. `/configuracion` — Gestión de bases de datos, plantilla de presupuesto, tasas de cambio
8. `/portfolio` — Portafolio de inversiones reales (acciones, ETFs, cripto, fondos)
9. `/fire` — Dashboard FIRE: independencia financiera, ratio, años restantes

---

## Código Existente

### `web_scrapping_email.py`

Ya existe y funciona. Lee Gmail vía IMAP usando `GMAIL_EMAIL` y `GMAIL_APP_PASSWORD` del `.env`. Parsea correos de Davivienda Colombia, Davivienda Panamá y Mastercard Black usando regex.

Funciones públicas a integrar:

- `fetch_transactions(since_date, max_emails)` → lista de dicts con transacciones.
- `fetch_emails_preview(since_date, max_emails)` → todas las transacciones incluyendo no-transacciones.

Este script debe ser llamado desde el backend como módulo, no como script standalone.

---

## Variables de Entorno (.env)

```
GMAIL_EMAIL=oscaredomejia@gmail.com
GMAIL_APP_PASSWORD=<app_password_de_gmail>
EXCHANGE_RATE_API_KEY=<api_key>
DATABASE_PATH=./data/finanzas.sqlite
```

---

## Convenciones de Desarrollo

- Backend en español para nombres de dominio (cuentas, transacciones, categorias), inglés para nombres técnicos (models, routers, services).
- Los endpoints REST siguen `/api/v1/{recurso}`.
- Todas las fechas en ISO 8601 (YYYY-MM-DD).
- Los montos se almacenan como `REAL` en SQLite, siempre con 2 decimales de precisión.
- No usar Ollama en la primera versión; el parsing es vía regex del script existente.

---

## Migraciones de Base de Datos

No se usa Alembic. Las migraciones se aplican automáticamente en `src/finance_app/database.py` mediante `_apply_sqlite_migrations()`, llamada desde `init_db()` al arrancar la app.

**Patrón para agregar una columna:**

1. Añadir `Column(...)` al modelo SQLAlchemy (cubre bases de datos nuevas via `create_all`).
2. Añadir una tupla `(tabla, columna, DDL)` a la lista `_MIGRATION_COLUMNS` en `database.py:326` (cubre bases existentes).
3. Si el campo debe aparecer en respuestas API, añadirlo a `to_dict()` del modelo.

```python
# database.py — helper idempotente
def ensure_sqlite_column(table_name, column_name, column_definition, engine_override=None):
    # Si la columna no existe en PRAGMA table_info, hace ALTER TABLE ADD COLUMN
    ...

# Entrada en _MIGRATION_COLUMNS:
("debts", "statement_day", "statement_day INTEGER"),
```

**Nuevas tablas** (sin tuplas de migración, las crea `create_all`): añadir el modelo a `models/__init__.py` y al import de `init_db()` en `database.py`.

---

## Campos extendidos — Modelo `Debt`

### Campos de tarjeta de crédito (añadidos)

| Campo | Tipo | Descripción |
|---|---|---|
| `statement_day` | `INTEGER` | Día del mes en que cierra el estado de cuenta (1-31) |
| `payment_due_day` | `INTEGER` | Día del mes límite de pago |
| `statement_balance` | `NUMERIC(18,2)` | Saldo capturado al último corte |
| `min_payment_percentage` | `FLOAT` | % del saldo para pago mínimo (ej: 5.0) |
| `monthly_interest_rate` | `FLOAT` | Tasa mensual efectiva explícita (ej: 1.9 = 1.9%/mes) |
| `rate_type` | `VARCHAR(20)` | `'fixed'` o `'variable'` |

### Campos existentes (referencia rápida)

- `interest_rate`: tasa anual en % — usada si `monthly_interest_rate` no está definida
- `annual_interest_rate`: tasa anual en decimal — alternativa a `interest_rate`
- `minimum_payment`: pago mínimo fijo almacenado
- `credit_limit`: cupo de la tarjeta
- `confirmed_balance` / `confirmed_balance_date`: balance confirmado desde estado de cuenta real

### Modelo `DebtInstallment` (`models/debt_installment.py`)

Compras diferidas en cuotas vinculadas a una tarjeta de crédito.

| Campo | Descripción |
|---|---|
| `debt_id` | FK a `debts.id` |
| `description` | Descripción de la compra |
| `total_amount` | Monto total de la compra |
| `installments_total` / `installments_paid` | Cuotas totales / ya pagadas |
| `monthly_amount` | Cuota mensual |
| `start_date` | Fecha de la primera cuota |
| `has_interest` | Si tiene interés diferido |

Properties calculadas: `installments_remaining`, `amount_remaining`, `amount_paid`.

---

## Módulo Simuladores (Fase 6)

Lógica portada desde `personal_finances/src/finance_app/services/`:

```
backend/services/simuladores/
├── __init__.py
├── deuda.py          # simulate_payoff() — avalancha/bola de nieve/abono extra
├── amortizacion.py   # AmortizationEngine — tabla mes a mes, modo hybrid
├── fondo_emergencia.py  # calcular_cobertura(), gastos_esenciales(), fondos_disponibles()
└── inversion.py      # simular_inversion() — función pura, sin DB
```

**Mapeo de modelos (`personal_finances` → nuevo proyecto):**
| Campo antiguo (Debt) | Campo nuevo (Cuenta) |
|---------------------------|--------------------------|
| `current_balance` | `saldo_actual` |
| `annual_interest_rate` | `tasa_interes` |
| `monthly_payment` | `cuota_mensual` |
| `original_amount` | `monto_original` |
| `start_date` | `fecha_inicio` |
| `term_months` | `plazo_meses` |
| `currency_code` | `moneda` |

**Endpoints simuladores:** `GET/POST /api/v1/simuladores/deuda`, `/fondo-emergencia`, `/inversion`, `/amortizacion/{cuenta_id}`

---

## Servicios de Deuda — Referencia Rápida

### `services/debt/`

| Archivo | Función principal |
|---|---|
| `amortization_engine.py` | `AmortizationEngine.generate_schedule(debt, mode)` — tabla mes a mes con interés |
| `amortization_service.py` | `ensure_debt_amortization_records(db, start, end)` — caché en `DebtAmortizationMonthly` |
| `balance_service.py` | `calculate_scheduled_principal_balance(debt, as_of_date)` |
| `helpers.py` | `calculate_credit_card_monthly_interest(debt)`, `calculate_suggested_minimum_payment(debt)`, `get_billing_cycle_info(debt)`, `debt_to_dict_with_calculated_balance(debt, db)` |
| `simulator.py` | `simulate_payoff(debts, extra_payment, strategy)`, `compare_strategies(debts, extra_payment)` |
| `cost_analysis.py` | `analyze_debt_cost(db, debt)` — histórico de pagos + proyección pago mínimo |
| `installments.py` | CRUD de `DebtInstallment` + `get_installments_summary(db, debt_id)` |

### `domain/debts/`

| Archivo | Función principal |
|---|---|
| `snapshot.py` | `build_debt_snapshots(db, start_month, end_month)`, `snapshot_after_payment(db, debt_id)` |
| `service.py` | `get_total_debt_principal_cop(db)` |
| `repository.py` | fetch/save snapshots, allocations |

### Endpoints de deuda (`api/debts.py`)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/debts/` | Lista de deudas activas |
| GET | `/debts/summary` | Totales + alertas utilización + alto interés |
| GET | `/debts/simulator` | Simulación con pago extra (query params) |
| GET | `/debts/strategy-comparison` | Avalancha vs bola de nieve vs mínimo |
| GET | `/debts/{id}` | Deuda individual |
| GET | `/debts/{id}/cost-analysis` | Costo histórico + proyección pago mínimo |
| GET | `/debts/{id}/billing-cycle` | Ciclo de facturación actual (tarjetas) |
| GET | `/debts/{id}/schedule` | Tabla de amortización (`mode=plan/actual/hybrid`) |
| GET/POST | `/debts/{id}/payments` | Historial / nuevo pago |
| DELETE | `/debts/{id}/payments/{pid}` | Eliminar pago |
| GET/POST | `/debts/{id}/installments` | Cuotas diferidas |
| PATCH/DELETE | `/debts/{id}/installments/{iid}` | Editar / eliminar cuota |
| GET | `/debts/{id}/installments/summary` | Resumen de diferidos |

### Convenciones de tasa de interés

- `monthly_interest_rate` (si definida) tiene prioridad sobre cualquier otra tasa en todos los cálculos.
- Fallback: `annual_interest_rate` (Numeric, puede ser decimal 0.12 o porcentaje 12).
- Fallback 2: `interest_rate` (Float, siempre en porcentaje, ej: 24.5).
- Conversión estándar: `monthly_rate = (1 + annual_decimal)^(1/12) - 1`.

---

## Módulo Portafolio de Inversiones (Fase 7)

### Modelos nuevos

| Modelo | Tabla | Descripción |
|---|---|---|
| `InvestmentPortfolio` | `investment_portfolios` | Agrupador de activos con target_allocation JSON |
| `InvestmentAsset` | `investment_assets` | Activo real: símbolo, unidades, precio_compra, tipo, asset_class |
| `AssetPriceHistory` | `asset_price_history` | Historial de precios manuales/API con UNIQUE (asset_id, fecha) |

Campos clave de `InvestmentAsset`: `simbolo`, `nombre`, `tipo` (accion/etf/cripto/fondo/otro), `asset_class` (renta_variable/renta_fija/liquidez/alternativo), `unidades`, `precio_compra`, `fecha_compra`, `moneda`, `activo`.

### Servicios nuevos

| Archivo | Responsabilidad |
|---|---|
| `services/portfolio_service.py` | CRUD portafolios y activos, cálculo ganancia/pérdida, allocation actual |
| `services/fire_service.py` | Ratio FIRE, ingreso pasivo, % independencia, proyección años restantes |
| `services/price_history_service.py` | Upsert de precios, historial, resumen consolidado de activos |

### Métricas calculadas por activo

- `precio_actual` = último precio en `asset_price_history`, o `precio_compra` si no hay historial
- `valor_actual` = `unidades × precio_actual`
- `costo_base` = `unidades × precio_compra`
- `ganancia` = `valor_actual − costo_base`
- `ganancia_pct` = `ganancia / costo_base × 100`

### Endpoints (`api/portfolio.py`, prefix `/api/v1/portfolio`)

| Método | Ruta | Descripción |
|---|---|---|
| GET/POST | `/` | Listar / crear portafolios |
| GET/DELETE | `/{portfolio_id}` | Detalle / eliminar portafolio |
| GET | `/{portfolio_id}/allocation` | Allocation actual vs target |
| GET/POST | `/assets` | Todos los activos con precios / crear activo |
| GET/DELETE | `/assets/{asset_id}` | Activo individual / soft delete |
| GET/POST | `/assets/{asset_id}/prices` | Historial de precios / registrar precio |

### Dashboard FIRE (`api/fire.py`, prefix `/api/v1/fire`)

`GET /` retorna:

```json
{
  "patrimonio_invertible": float,
  "gastos_anuales_esenciales": float,
  "ingreso_pasivo_anual": float,
  "ratio_fire": float,
  "independencia_pct": float,
  "ingreso_pasivo_vs_gastos_pct": float,
  "anos_restantes": float | null
}
```

Regla: `ratio_fire = patrimonio_invertible / (gastos_anuales × 25)` (regla del 4%).

---

## Mejoras de Presupuesto (portadas de personal_finances)

- `_cascade_future_months(db, categoria_id, desde_mes)` — cuando se edita `asignado`, propaga el cambio a todos los meses futuros que no hayan sido sobreescritos manualmente.
- `listo_para_asignar(db)` — suma de saldos en cuentas de ahorro menos total `disponible` en presupuesto. Aparece en dashboard y página de presupuesto.
- `historial_categoria(db, categoria_id, meses)` — N meses de asignado/gastado/disponible para una categoría.
- `inicializar_mes` mejorado — hereda `asignado` del mes anterior; para categorías ahorro calcula `monto_inicial` desde el `disponible` anterior.

# Reglas para el Agente

## Antes de implementar

Antes de generar código:

1. Analizar arquitectura existente.
2. Proponer estructura de carpetas.
3. Definir entidades y relaciones.
4. Definir flujo de datos frontend/backend.
5. Identificar componentes reutilizables.
6. Dividir implementación por fases.

## Implementación

- Implementar cambios pequeños y modulares.
- Evitar archivos excesivamente grandes.
- No mezclar lógica de negocio con UI.
- Priorizar mantenibilidad sobre rapidez.
- Evitar duplicación de código.
- Mantener nombres consistentes.
-

## Frontend

- Usar JavaScript vanilla (ES6+ con módulos nativos), sin frameworks ni bundlers.
- Organizar por módulos: cada página tiene su propio archivo JS en `js/pages/`.
- Extraer lógica reutilizable a `js/components/` y llamadas API a `js/api/`.
- Mantener páginas ligeras; la lógica compleja va en módulos separados.
- Mantener diseño consistente usando variables CSS (`--color-*`, `--spacing-*`, etc.).

## Backend

- Mantener routers delgados.
- La lógica debe vivir en services.
- Validaciones en schemas.
- Mantener separación clara de responsabilidades.

## UX

- Priorizar claridad visual.
- Evitar interfaces sobrecargadas.
- Mantener navegación intuitiva.
- Usar feedback visual para acciones importantes.

## Restricciones

- No reutilizar componentes legacy.
- No implementar dark mode.
- No agregar funcionalidades no solicitadas.
- No modificar automáticamente datos financieros sin confirmación explícita.

---

## Roadmap — Features Pendientes

### Nivel 2 — Análisis avanzado (próxima sesión)

**Tasa de ahorro real (Savings Rate)**
- KPI central: `(ingresos - gastos) / ingresos * 100`
- Mostrar en dashboard y en página de Ingresos
- Histórico mensual de savings rate en gráfico de línea
- Meta de savings rate configurable (alertar si baja)
- Backend ya existe: `GET /api/reports/savings-rate`

**Valor neto histórico (Net Worth timeline)**
- Snapshot mensual de patrimonio neto: activos - pasivos
- Gráfico de evolución histórica mes a mes
- Requiere tabla `net_worth_snapshots (month, assets_cop, liabilities_cop, net_cop)`
- Calcular automáticamente al inicio de cada mes o bajo demanda

**Análisis de gastos discrecionales vs esenciales**
- Campo `is_essential` ya existe en `Category`
- Crear reporte mensual: % gasto esencial vs discrecional
- Comparativo histórico y benchmarks (ej: regla 50/30/20)
- Vista de semáforo por categoría

---

### Nivel 3 — Features diferenciadores (sesiones futuras)

**Reglas de categorización automática**
- Motor de reglas: `{campo: 'payee', contiene: 'Rappi'} → categoría: Comidas`
- `MerchantRule` ya existe — extender para cubrir todos los campos de transacción
- Aplicar automáticamente al importar Gmail y al crear transacciones manuales
- UI de gestión de reglas mejorada con testing en tiempo real

**Metas financieras con tracking avanzado**
- `Goal` ya existe — mejorar con:
  - Barra de progreso visual en dashboard
  - Cálculo automático: "necesito ahorrar $X/mes para llegar a tiempo"
  - Alerta si el ritmo actual no alcanza la meta
  - Vinculación con categorías de presupuesto

**Alertas inteligentes**
- Reglas basadas en patrones: "gasto 40% más que promedio en X categoría"
- Alertas de fondo de emergencia (si baja de N meses de cobertura)
- Alertas de ratio FIRE (si no avanza en N meses)
- `AlertRule` ya existe — extender para alertas de tendencia, no solo threshold

**Importador CSV bancario**
- Importar extractos de Davivienda Colombia (CSV/XLS)
- Mapeo de columnas configurable
- Deduplicación por fecha+monto+descripción
- Vista de revisión antes de confirmar importación
- Historial de importaciones con rollback
