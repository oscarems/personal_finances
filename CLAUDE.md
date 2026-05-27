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

No se usa Alembic. Las migraciones se aplican en `backend/db/session.py` mediante la función `aplicar_migraciones(engine)`, que usa `PRAGMA table_info` para detectar columnas faltantes y añadirlas con `ALTER TABLE ADD COLUMN`. Esta función se llama en `create_tables()` antes de crear tablas nuevas.

**Patrón:**

```python
def _add_column_if_missing(conn, table: str, column: str, definition: str):
    cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
    if column not in cols:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
```

---

## Campos extendidos (portados desde personal_finances)

### Cuenta (backend/models/cuenta.py)

Nuevos campos para el motor de amortización:

- `fecha_inicio: date | None` — fecha en que inició el préstamo/hipoteca
- `plazo_meses: int | None` — plazo en meses (para generar tabla de amortización)

### Categoria (backend/models/categoria.py)

Nuevos flags para el simulador de fondo de emergencia:

- `es_esencial: bool = False` — categoría de gasto esencial (base del cálculo)
- `es_fondo_emergencia: bool = False` — categoría de ahorro que forma el fondo

### PresupuestoMes (backend/models/presupuesto.py)

Nuevos campos para cascada y acumulación de ahorros:

- `asignado_sobreescrito: bool = False` — indica si el usuario editó el valor manualmente
- `monto_inicial: float = 0.0` — disponible acumulado del mes anterior (solo categorías ahorro)
- `monto_inicial_sobreescrito: bool = False` — indica si el monto_inicial fue editado manualmente

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
