# 💰 Personal Finances

Aplicación de finanzas personales estilo YNAB (You Need A Budget) construida con FastAPI y Python.

**🌟 Versión Multi-Moneda con Soporte Completo COP/USD**

---

## ✨ Características Principales

### 💼 Gestión Financiera Core
- **Presupuesto estilo YNAB**: Dale un propósito a cada peso con el principio "Give every dollar a job"
- **Ready to Assign Unificado**: Ve todo tu dinero sin importar la moneda
- **Rollover Inteligente**: Categorías que acumulan (ahorros) o reinician (gastos mensuales)
- **8 Tipos de Cuentas**: Corriente, ahorros, tarjetas de crédito, hipotecas, CDT, inversiones, efectivo

### 🌍 Multi-Moneda Avanzado
- **Soporte COP y USD**: Cada cuenta tiene una moneda oficial
- **Conversiones Automáticas**: Ver equivalentes en tiempo real
- **Presupuesto Unificado**: Suma asignaciones de ambas monedas convertidas
- **Tasas de Cambio Reales**: Desde API con fallback inteligente (4000 por defecto)
- **Transferencias Multi-Moneda**: Transfiere entre cuentas de diferentes monedas

#### ✅ Auditoría Multi-Moneda (Transacciones)
Cada transacción conserva campos de auditoría para trazabilidad completa:
- **Monto original + moneda original** (lo que ingresó el usuario)
- **Tasa FX usada** (USD/COP) cuando aplica conversión
- **Monto en moneda base** (para reportes y reconciliación)

> **Nota:** Si actualizas desde una versión anterior con datos existentes, debes ejecutar un backfill
> para poblar estos campos con tasas históricas apropiadas o reimportar tu histórico.

### 📊 Transacciones y Reportes
- **Transferencias Inteligentes**: Sistema completo de transferencias entre cuentas
- **Importador YNAB**: Importa tus datos existentes desde archivos CSV
- **Transacciones Recurrentes**: Automatiza pagos regulares
- **Dashboard Visual**: Gráficos y reportes para entender tus finanzas
- **Reconciliación**: Marca transacciones como verificadas

### ⚡ Performance
- **Queries Optimizadas**: Eager loading elimina problema N+1
- **Cache de Tasas**: Conversiones rápidas sin queries repetidas
- **Batch Operations**: Procesamiento eficiente de múltiples registros

---

## 🚀 Inicio Rápido

### Requisitos
- Python 3.8+
- pip

### 1. Clonar e Instalar

```bash
# Clonar repositorio
git clone [tu-repo]
cd personal_finances

# Instalar dependencias
pip install -r requirements.txt
```

### 2. Inicializar Base de Datos

```bash
python src/finance_app/scripts/init_db.py
```

Esto creará:
- ✅ Base de datos SQLite en `data/finances.db`
- ✅ Monedas (COP y USD)
- ✅ Categorías YNAB predefinidas (Needs, Hogar, Deudas, Streaming, etc.)
- ✅ Grupos de categorías organizados
- ✅ Cuentas de ejemplo (opcional)

#### 🧪 Modo demo (sin borrar tu base real)

Puedes levantar una versión demo que usa **otra base de datos** y se crea sola si no existe. También puedes cambiarla desde la UI (selector "Base de datos" en el sidebar).

```bash
DEMO_MODE=true python run.py
```

Esto usará `data/finances_demo.db` y no toca `data/finances.db`. Si el archivo demo no existe, se inicializa automáticamente con datos base.

#### 🗂️ Múltiples bases locales (personal, pareja, amigo)

Desde el selector "Base de datos" en el sidebar puedes elegir o crear nuevas bases locales sin variables de entorno.
Cada nombre crea un archivo SQLite en `data/<nombre>.db` (ej: `data/pareja.db`). Si no hay ninguna base,
la app crea y usa automáticamente la demo.

#### 🔐 Conectar a otra base usando credenciales

Si quieres apuntar a otra base (por ejemplo PostgreSQL) sin tocar tu SQLite local, define `DATABASE_URL`:

```bash
DATABASE_URL="postgresql+psycopg2://usuario:password@localhost:5432/finanzas" python run.py
```

> Si `DATABASE_URL` está definido, se ignora `DEMO_MODE` y el archivo SQLite local.

### 3. Ejecutar la Aplicación

```bash
python run.py
```

La aplicación estará disponible en:
- **App**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Dashboard**: http://localhost:8000/

---

## 📖 Documentación

- **[TUTORIAL.md](TUTORIAL.md)**: Guía completa de uso paso a paso
- **[YNAB_FEATURES_COMPARISON.md](YNAB_FEATURES_COMPARISON.md)**: Comparación con YNAB y roadmap

---

## 🎯 Conceptos Clave

### Ready to Assign (Disponible para Asignar)

```
Ready to Assign = Total en TODAS las Cuentas - Total Asignado en Presupuesto
```

El objetivo es llevar esto a $0 asignando cada peso a una categoría.

### Categorías con Rollover

**🔁 Reset (Reiniciar):**
- Lo no gastado vuelve a "Ready to Assign" el próximo mes
- Para: Mercado, servicios, transporte

**🔄 Accumulate (Acumular):**
- Lo no gastado se acumula en la categoría
- Para: Emergencias, vacaciones, ahorros

### Presupuesto Multi-Moneda

- Puedes asignar en COP o USD a cualquier categoría
- El sistema suma todo convertido a la moneda que estés viendo
- Cambiar moneda solo cambia la visualización, no separa los datos

---

## 🏦 Tipos de Cuenta

| Tipo | Icono | Campos Especiales |
|------|-------|-------------------|
| Cuenta Corriente | 💳 | - |
| Cuenta de Ahorros | 🏦 | Tasa de interés |
| Tarjeta de Crédito | 💳 | Cupo, día de pago |
| Crédito Libre Inversión | 💰 | Tasa, cuota mensual, monto original |
| Hipoteca | 🏠 | Tasa, cuota mensual, monto original |
| CDT | 📜 | Tasa, monto original, fecha vencimiento |
| Inversión | 📈 | - |
| Efectivo | 💵 | - |

---

## 📁 Estructura del Proyecto

```
personal_finances/
├── run.py                  # Ejecutar app
├── web_scrapping_email.py  # Script intocable
├── config.py               # Configuración + ACCOUNT_TYPES
├── requirements.txt        # Dependencias
├── data/                   # SQLite + uploads
├── src/
│   └── finance_app/
│       ├── app.py             # App FastAPI principal
│       ├── api/               # Endpoints REST
│       ├── models/            # Modelos SQLAlchemy
│       ├── services/          # Lógica de negocio
│       ├── utils/             # Utilidades
│       ├── templates/         # Templates Jinja2
│       ├── static/            # Assets estáticos
│       └── scripts/           # Scripts de mantenimiento
├── docs/                   # Documentación del proyecto
└── tests/                  # Pruebas automatizadas
```

---

## 🔄 Transferencias entre Cuentas

### Crear Transferencia

**En UI:**
1. Ve a "Transacciones"
2. Click "⇄ Nueva Transferencia" (botón verde)
3. Selecciona cuenta origen y destino
4. Selecciona monedas (pueden ser diferentes)
5. Ingresa monto
6. Guardar

**Resultado:**
- ✅ Crea 2 transacciones vinculadas
- ✅ Actualiza balances automáticamente
- ✅ Convierte monedas si son diferentes
- ✅ Al eliminar una, elimina ambas

**Ejemplo:**
```
Transferir $100 USD de Ahorros USD → Corriente COP

Resultado:
  - Ahorros USD: -$100.00 USD
  - Corriente COP: +$400,000 COP (con tasa 4000)
```

---

## 💱 Sistema de Tasas de Cambio

### Fallback Inteligente

El sistema busca tasas en este orden:

1. **Tasa del día en DB** (si existe)
2. **API Principal** (exchangerate-api.com) - 2 intentos
3. **API Fallback** (exchangerate.host) - 2 intentos
4. **Promedio últimos 5 días** del histórico
5. **Tasa por defecto** (4000 COP/USD)

### Configuración

En `config.py`:

```python
EXCHANGE_RATE_API = {
    'primary': 'https://api.exchangerate-api.com/v4/latest/USD',
    'fallback': 'https://api.exchangerate.host/latest?base=USD',
    'timeout': 5,
    'retries': 2,
    'fallback_average_days': 5,
    'default_rate': 4000
}
```

---

## 📥 Importar desde YNAB

### Pasos:

1. **Exportar desde YNAB:**
   - Click en nombre del presupuesto
   - "Export Budget Data"
   - Selecciona "Register"
   - Descarga CSV

2. **Importar en la App:**
   - Ve a `/import`
   - Selecciona archivo CSV
   - Click "Importar"

### El sistema detecta:
- ✅ Categorías por nombre (formato "Grupo: Categoría")
- ✅ Transferencias (busca Transfer: en payee)
- ✅ Fechas DD/MM/YYYY
- ✅ Cuentas por nombre
- ✅ Duplicados (import_id)

---

## 🎨 Uso del Presupuesto

### Workflow YNAB:

1. **Registra ingresos** (monto positivo)
2. **Mira "Ready to Assign"** en banner azul
3. **Asigna a categorías** hasta llegar a $0
4. **Registra gastos** (monto negativo)
5. **Ajusta presupuesto** si te pasas

### Presupuesto Multi-Moneda:

**Selector arriba:**
- COP: Ve todo en pesos colombianos
- USD: Ve todo en dólares

**¿Cómo suma?**
```
Asignaste:
  - $100 USD a "Mercado"
  - $400,000 COP a "Mercado"

En vista COP:
  Mercado: $800,000 COP (suma convertida)

En vista USD:
  Mercado: $200 USD (suma convertida)
```

---

## 📊 API REST

Documentación interactiva: http://localhost:8000/docs

### Endpoints Principales:

**Cuentas:**
```bash
GET    /api/accounts/              # Listar cuentas
POST   /api/accounts/              # Crear cuenta
PUT    /api/accounts/{id}          # Actualizar cuenta
DELETE /api/accounts/{id}          # Cerrar cuenta
GET    /api/accounts/summary       # Resumen con totales
```

**Transacciones:**
```bash
GET    /api/transactions/          # Listar transacciones
POST   /api/transactions/          # Crear transacción
PUT    /api/transactions/{id}      # Actualizar
DELETE /api/transactions/{id}      # Eliminar
POST   /api/transactions/transfer  # 🆕 Crear transferencia
```

**Presupuesto:**
```bash
GET    /api/budgets/current        # Presupuesto mes actual
GET    /api/budgets/month/{y}/{m}  # Presupuesto mes específico
POST   /api/budgets/assign         # Asignar dinero a categoría
```

**Tasas de Cambio:**
```bash
GET    /api/exchange-rates/current      # Tasa actual
GET    /api/exchange-rates/history      # Histórico
GET    /api/exchange-rates/convert      # Convertir monto
```

**Importar:**
```bash
POST   /api/import/ynab            # Importar CSV YNAB
```

---

## 🛠️ Tecnologías

**Backend:**
- **FastAPI** - Framework web moderno y rápido
- **SQLAlchemy** - ORM con eager loading optimizado
- **SQLite** - Base de datos embebida
- **Pandas** - Procesamiento CSV
- **Requests** - HTTP client para APIs de tasas
- **Uvicorn** - Servidor ASGI

**Frontend:**
- **HTML5 + Jinja2** - Templating
- **Tailwind CSS** - Diseño moderno y responsive
- **Chart.js** - Gráficos interactivos
- **Vanilla JavaScript** - Sin frameworks pesados

**Optimizaciones:**
- Eager loading con `joinedload()`
- Cache de tasas de cambio en memoria
- Batch queries para presupuestos
- Commits optimizados (1 vs N)

---

## 🔧 Desarrollo

### Reinstalar Base de Datos

**⚠️ CUIDADO: Esto borra todos los datos**

```bash
# Windows
del data\finances.db

# Linux/Mac
rm data/finances.db

# Luego
python src/finance_app/scripts/init_db.py
```

### Ejecutar en Modo Debug

```bash
# El servidor se recarga automáticamente
python run.py
```

### Ver Logs

```bash
# Logs aparecen en consola
# Nivel DEBUG muestra queries SQL
```

### Estructura de Base de Datos

```sql
-- Principales tablas
accounts            -- Cuentas con campos opcionales
transactions        -- Transacciones con transfer_account_id
categories          -- Con rollover_type
category_groups     -- Grupos de categorías
budget_months       -- Asignaciones mensuales
exchange_rates      -- Tasas históricas USD-COP
recurring_transactions -- Transacciones automáticas
currencies          -- COP y USD
payees             -- Beneficiarios
```

---

## 🚀 Próximas Características (Roadmap)

### Fase 1: Core Features (1-2 semanas)
- [ ] Split Transactions (dividir transacciones)
- [ ] Goals/Metas con tracking visual
- [ ] Age of Money
- [ ] Reconciliation workflow completo

### Fase 2: Enhanced UX (1 semana)
- [ ] Dashboard con datos reales (gráficos)
- [ ] Búsqueda avanzada de transacciones
- [ ] Reports avanzados (mes a mes)
- [ ] Net Worth tracking

### Fase 3: Advanced (2-3 semanas)
- [ ] Credit card payment tracking especial
- [ ] Scheduled transactions con aprobación
- [ ] Undo/Redo
- [ ] Exportar a CSV/Excel

### Fase 4: Platform
- [ ] PWA básico (Progressive Web App)
- [ ] Multi-usuario + autenticación
- [ ] Backup automático
- [ ] Import OFX/QFX

---

## 🐛 Troubleshooting

### "no such column: accounts.interest_rate"

**Problema:** Base de datos desactualizada

**Solución:**
```bash
del data/finances.db  # Borra DB
python src/finance_app/scripts/init_db.py  # Recrea con nuevo schema
```

### "No module named finance_app"

**Solución:**
- Ejecuta desde la raíz del proyecto
- Verifica que `src/finance_app/` tenga `__init__.py`
- Instala dependencias: `pip install -r requirements.txt`

### Gráficos no cargan

**Problema:** Chart.js no cargó desde CDN

**Solución:**
- Verifica conexión a internet
- Abre DevTools (F12) y revisa errores de consola

### Tasa de cambio incorrecta

**Problema:** APIs no responden

**Solución:**
- El sistema usa fallback automático
- Última opción: default 4000
- Para forzar actualización: reinicia servidor

### Importador YNAB falla

**Problemas comunes:**
- Fechas con formato ########: Se omiten
- Categorías no existen: Crea en la app primero
- Cuentas no existen: Crea en la app primero

**Solución:**
- Revisa preview de errores al importar
- Ajusta CSV si es necesario
- Crea categorías/cuentas faltantes

---

## 📈 Mejoras de Performance

### Antes vs Después:

**Presupuesto con 50 categorías:**
- Antes: ~200 queries (N+1 problem)
- Después: 4 queries (batch + eager loading)
- **Mejora: 50x más rápido** ⚡

**Optimizaciones implementadas:**
1. Eager loading: `joinedload()` para relaciones
2. Batch queries: Una query para todos los budgets
3. Cache de currencies en memoria
4. Cache de tasas de cambio (no queries repetidas)
5. Un commit al final vs múltiples en loops

---

## 🏆 Ventajas sobre YNAB

1. **Multi-moneda nativo** 🌍
   - YNAB: No soporta múltiples monedas
   - Nosotros: COP/USD integrado con conversión automática

2. **Tipos de cuenta avanzados** 🏦
   - YNAB: Solo checking/savings
   - Nosotros: 8 tipos especializados

3. **Código abierto** 💻
   - YNAB: Propietario
   - Nosotros: Modificable y extensible

4. **Sin suscripción** 💰
   - YNAB: $14.99/mes
   - Nosotros: Gratis

5. **Transferencias multi-moneda** 🔄
   - YNAB: Solo misma moneda
   - Nosotros: Con conversión automática

6. **Performance optimizado** ⚡
   - Queries optimizadas desde el inicio
   - Cache inteligente

---

## 📚 Recursos Adicionales

- **[TUTORIAL.md](TUTORIAL.md)**: Tutorial completo paso a paso
- **[YNAB_FEATURES_COMPARISON.md](YNAB_FEATURES_COMPARISON.md)**: Comparación detallada con YNAB
- **API Docs**: http://localhost:8000/docs
- **Metodología YNAB**: https://www.youneedabudget.com/the-four-rules/

---

## 🤝 Contribuir

Para contribuir:
1. Fork el repo
2. Crea una rama para tu feature
3. Haz tus cambios
4. Submit un Pull Request

---

## 📄 Licencia

Este proyecto es de uso personal. Basado en la metodología YNAB pero sin afiliación oficial.

---

## 👨‍💻 Créditos

**Creado con ❤️ para gestionar finanzas personales de forma simple y efectiva.**

**Metodología:** Inspirado en YNAB (You Need A Budget)
**Stack:** FastAPI, SQLAlchemy, SQLite, Tailwind CSS
**Performance:** Optimizado con eager loading y caching

---

**¡Feliz presupuesto! 💰**
