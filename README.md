# Personal Finances

Aplicación de finanzas personales estilo YNAB construida con FastAPI + SQLAlchemy + Jinja2. Multi-moneda (COP/USD), presupuesto, deudas, patrimonio neto y simulación de inversiones.

---

## Características

- **Presupuesto YNAB**: Categorías con rollover (ahorro acumulativo vs gasto mensual), Ready to Assign, asignaciones multi-moneda
- **Multi-moneda**: COP y USD con conversión automática, tasas desde API con fallback, auditoría FX por transacción
- **Patrimonio**: Activos (inmuebles, vehículos, otros) con depreciación y rendimiento. Deudas integradas desde el módulo de deudas. Timeline de patrimonio neto
- **Deudas**: Hipotecas, créditos de consumo, tarjetas. Motor de amortización con pagos reales + proyectados. Timeline de saldo principal
- **Metas financieras**: Tracking visual de objetivos de ahorro
- **Fondo de emergencia**: Cálculo y seguimiento
- **Reportes**: Gastos por categoría/tag/grupo, ingresos vs gastos, tendencias de balance, salud financiera
- **Simulador de inversiones**: Proyecciones con interés compuesto
- **Importador YNAB**: CSV con detección de categorías, transferencias y duplicados
- **Transacciones recurrentes**: Automatización de pagos regulares
- **Integración Gmail**: Scraping de transacciones desde correos bancarios
- ~~**Integración Telegram**~~ *(deprecada)*

---

## Inicio Rápido

### Requisitos

- Python 3.8+

### Instalación

```bash
git clone https://github.com/oscarems/personal_finances.git
cd personal_finances
pip install -r requirements.txt
```

### Inicializar BD

```bash
python src/finance_app/scripts/init_db.py
```

Crea SQLite en `data/finances.db` con monedas, categorías y grupos predefinidos.

### Ejecutar

```bash
python run.py
```

- App: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Modo Demo

```bash
DEMO_MODE=true python run.py
```

Usa `data/finances_demo.db` sin tocar tu base real. También puedes cambiar la base desde el selector en el sidebar.

### Base de datos externa

```bash
DATABASE_URL="postgresql+psycopg2://user:pass@localhost:5432/finanzas" python run.py
```

---

## Arquitectura

```
src/finance_app/
├── app.py                    # FastAPI app + registro de rutas
├── database.py               # Engine SQLAlchemy, sesiones
├── config/settings.py        # Configuración centralizada
├── models/                   # Modelos ORM
│   ├── patrimonio_asset.py   # Activos con depreciación/rendimiento
│   ├── debt.py               # Deudas + pagos
│   └── debt_amortization.py  # Amortización mensual
├── domain/                   # Lógica de dominio
│   ├── debts/                # Proyecciones, snapshots, repositorio
│   └── fx/                   # Conversión de moneda
├── api/                      # Routers FastAPI
│   ├── patrimonio.py         # CRUD activos + resumen/timeline
│   ├── debts.py              # CRUD deudas + amortización
│   ├── budgets.py            # Presupuesto mensual
│   ├── reports_pkg/          # Reportes modulares (spending, income, balance, debt)
│   └── ...                   # accounts, goals, transactions, etc.
├── services/                 # Lógica de negocio
│   ├── debt/                 # Amortización, balance, timeline
│   ├── patrimonio/           # Valoración de activos, patrimonio neto
│   ├── mortgage/             # Cálculos hipotecarios
│   └── ...                   # budget, transaction, alert, etc.
├── templates/                # Jinja2 + Tailwind CSS
└── scripts/                  # Migración, importación, seeds
```

### Convenciones de código

| Aspecto | Convención |
|---------|-----------|
| Moneda en modelos | `Numeric(18, 2)` — nunca `Float` |
| Fechas | `datetime.date`, columnas `Date` |
| Tasas de interés | Decimales (0.08 = 8%), anuales por defecto |
| Transacciones | Negativo = gasto, positivo = ingreso |
| Imports | Absolutos: `from finance_app.xxx import ...` |
| Config | `from finance_app.config import ...` |
| UI | Español, Tailwind utility classes |
| API responses | Siempre incluir dict `currency` en valores monetarios |

### Capas

- **Calculators** (`services/*/calculator.py`): Funciones puras sin acceso a BD. Reciben objetos, retornan datos.
- **Services** (`services/*_service.py`): Orquestación con acceso a BD. Llaman a calculators para la lógica.
- **API routers** (`api/*.py`): Capa HTTP delgada. Validación, llamada a services, formato de respuesta. Sin lógica de negocio.

### Tasas de interés

- **Colombia (EA)**: Tasa efectiva anual → `mensual = (1 + anual)^(1/12) - 1`
- **EEUU (APR)**: Tasa nominal → `mensual = anual / 12`
- Default: `effective`. Documentar convención en `debt.notes`.

---

## Módulos Principales

### Presupuesto

- **Ready to Assign** = Total en cuentas - Total asignado
- **Rollover Reset**: Lo no gastado vuelve a Ready to Assign el próximo mes (gastos mensuales)
- **Rollover Accumulate**: Lo no gastado se acumula (ahorros, metas)
- Asignaciones en COP o USD, suma convertida a la moneda de visualización

### Patrimonio

Sistema unificado de patrimonio neto:
- **Activos**: `inmueble`, `vehiculo`, `otro` con métodos de depreciación (línea recta, saldo decreciente, doble saldo)
- **Deudas**: Lee directamente del modelo `Debt` (hipotecas + créditos de consumo). No duplica datos.
- **Valoración**: Anual desde fecha de adquisición con tasa de retorno configurable
- **Timeline**: 24 meses pasados + 24 futuros

### Deudas

- Tipos: `mortgage`, `credit_loan`, `credit_card`
- Motor de amortización híbrido: pagos reales registrados + proyección futura
- Timeline de saldo principal con proyecciones
- Tarjetas de crédito solo en `/debts`, no en patrimonio

### Reportes

Módulo `api/reports_pkg/` con archivos separados:
- `spending.py` — Gastos por categoría, tag, grupo, tendencias
- `income.py` — Ingresos vs gastos, presupuesto vs real, tasa de ahorro
- `balance.py` — Tendencia de balance, historial por cuenta
- `debt.py` — Historial de deuda, timeline principal, proyección de liquidación

---

## API REST

Documentación interactiva en http://localhost:8000/docs

```
GET/POST       /api/accounts/              # Cuentas
GET/POST       /api/transactions/          # Transacciones
POST           /api/transactions/transfer  # Transferencias
GET/POST       /api/budgets/               # Presupuesto
GET/POST/PUT   /api/debts/                 # Deudas
GET/POST/PUT/DELETE /api/patrimonio/activos/  # Activos patrimonio
GET            /api/patrimonio/resumen     # Resumen patrimonio
GET            /api/patrimonio/timeline    # Timeline patrimonio neto
GET            /api/reports/               # Reportes
GET            /api/exchange-rates/        # Tasas de cambio
POST           /api/import/ynab            # Importar YNAB CSV
GET/POST       /api/goals/                 # Metas financieras
```

---

## Testing

```bash
# Todos los tests
python -m pytest tests/ -v

# Test específico
python -m pytest tests/test_patrimonio_calculator.py -v
```

- Tests de calculators con valores esperados hardcoded y tolerancias explícitas
- `SimpleNamespace` o dataclasses para mock de modelos (sin BD cuando sea posible)
- Tests de API con SQLite in-memory y override de `get_db`

---

## Configuración Opcional

### Integración con Gmail (opcional)

Permite que la app lea correos bancarios y los importe como transacciones
automáticamente. Requiere una cuenta Gmail y configuración de acceso seguro.

#### Paso a paso para configurar

**1. Habilitar IMAP en Gmail**
1. Abre Gmail → Configuración (ícono de engranaje) → Ver todos los ajustes
2. Ve a la pestaña **"Reenvío y correo POP/IMAP"**
3. En la sección IMAP, selecciona **"Habilitar IMAP"**
4. Guarda los cambios

**2. Activar verificación en dos pasos**
1. Ve a [myaccount.google.com/security](https://myaccount.google.com/security)
2. En "Cómo inicias sesión en Google", activa **"Verificación en dos pasos"**
3. Sigue el asistente de configuración

**3. Generar una App Password**
1. Ve a [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. En "Seleccionar aplicación" elige **"Correo"**
3. En "Seleccionar dispositivo" elige **"Otro (nombre personalizado)"** → escribe `fincas`
4. Haz clic en **Generar**
5. Copia la contraseña de 16 caracteres (formato: `xxxx xxxx xxxx xxxx`)

**4. Configurar en .env**

```bash
GMAIL_EMAIL="tucorreo@gmail.com"
GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
```

> ⚠️ Usa la App Password generada, **no** tu contraseña normal de Gmail.
> La App Password tiene espacios — cópiala exactamente como aparece.

**Correos bancarios soportados actualmente:**
- Bancolombia (Colombia)
- BAC / bancos Panamá
- Mastercard Black

Una vez configurado, ve a **Avanzado → Importar Gmail** en la aplicación
para revisar y registrar los correos detectados.

### Tasas de Cambio

Fallback en orden: tasa del día en BD → API primaria → API fallback → promedio últimos 5 días → default (4000 COP/USD).

---

## Tech Stack

- **Backend**: FastAPI + Uvicorn + SQLAlchemy (SQLite)
- **Frontend**: Jinja2 + Tailwind CSS (CDN) + Chart.js + Vanilla JS
- **Testing**: pytest

---

## Licencia

Proyecto de uso personal. Inspirado en la metodología YNAB.
