# 💰 Personal Finances

Aplicación de finanzas personales estilo YNAB (You Need A Budget) construida con FastAPI y Python.

## ✨ Características

- **Presupuesto estilo YNAB**: Dale un propósito a cada peso con el principio "Give every dollar a job"
- **Multi-moneda**: Maneja cuentas en COP y USD simultáneamente
- **Importador YNAB**: Importa tus datos existentes desde archivos CSV de YNAB
- **Dashboard visual**: Gráficos y reportes para entender tus finanzas
- **Transacciones**: Registra ingresos y gastos con categorización
- **Múltiples cuentas**: Gestiona cuentas corrientes, ahorros, tarjetas de crédito y efectivo

## 🚀 Inicio Rápido

### 1. Instalar Dependencias

```bash
pip install -r requirements.txt
```

### 2. Inicializar Base de Datos (Primera vez)

```bash
python backend/init_db.py
```

Esto creará:
- Base de datos SQLite en `data/finances.db`
- Monedas (COP y USD)
- Categorías predefinidas
- Cuentas de ejemplo

### 3. Ejecutar la Aplicación

```bash
python run.py
```

La aplicación estará disponible en:
- **App**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## 📁 Estructura del Proyecto

```
personal_finances/
├── backend/
│   ├── models/          # Modelos SQLAlchemy (DB)
│   ├── services/        # Lógica de negocio
│   ├── api/             # Endpoints FastAPI
│   ├── utils/           # Utilidades (importador YNAB)
│   ├── app.py           # Aplicación FastAPI principal
│   ├── database.py      # Configuración de DB
│   └── init_db.py       # Script de inicialización
├── frontend/
│   ├── templates/       # Templates HTML con Jinja2
│   └── static/          # CSS/JS (Tailwind via CDN)
├── data/
│   ├── finances.db      # Base de datos SQLite
│   └── uploads/         # Archivos CSV importados
├── config.py            # Configuración general
├── requirements.txt     # Dependencias Python
└── run.py              # Script para ejecutar la app
```

## 💵 Configuración de Monedas

Por defecto, la app maneja COP y USD. Para actualizar tasas de cambio, edita `config.py`:

```python
DEFAULT_EXCHANGE_RATES = {
    'COP': 1.0,      # Moneda base
    'USD': 4000.0    # 1 USD = 4000 COP
}
```

## 📥 Importar desde YNAB

1. Exporta tus datos desde YNAB en formato CSV
2. Ve a la página "Importar YNAB" en la app
3. Selecciona la moneda correspondiente
4. Sube el archivo CSV

El importador detecta automáticamente:
- Categorías con formato "Grupo: Categoría"
- Transferencias entre cuentas
- Transacciones duplicadas
- Fechas en diferentes formatos

## 🎯 Uso del Presupuesto (Estilo YNAB)

1. **Asigna dinero a categorías**: En la página "Presupuesto", haz clic en cualquier categoría para asignar dinero
2. **"Ready to Assign"**: El banner azul muestra cuánto dinero tienes sin asignar
3. **Barras de progreso**: Visualiza qué porcentaje de tu presupuesto has gastado en cada categoría
4. **Multi-moneda**: Cambia entre COP y USD en el selector superior

## 🏦 Gestión de Cuentas

Tipos de cuenta soportados:
- **Checking**: Cuenta corriente
- **Savings**: Ahorros
- **Credit Card**: Tarjeta de crédito
- **Cash**: Efectivo

Cada cuenta tiene:
- Nombre personalizable
- Tipo
- Moneda (COP o USD)
- Saldo actual

## 📊 API REST

La aplicación incluye una API REST completa. Documentación interactiva disponible en:
- http://localhost:8000/docs (Swagger UI)

### Principales Endpoints:

- `GET /api/accounts/` - Listar cuentas
- `POST /api/accounts/` - Crear cuenta
- `GET /api/transactions/` - Listar transacciones
- `POST /api/transactions/` - Crear transacción
- `GET /api/budgets/current` - Presupuesto actual
- `POST /api/budgets/assign` - Asignar dinero a categoría
- `POST /api/import/ynab` - Importar CSV de YNAB

## 🛠️ Tecnologías

**Backend:**
- FastAPI (framework web moderno y rápido)
- SQLAlchemy (ORM)
- SQLite (base de datos)
- Pandas (procesamiento CSV)
- Uvicorn (servidor ASGI)

**Frontend:**
- HTML5 + Jinja2
- Tailwind CSS (diseño moderno y responsive)
- Chart.js (gráficos)
- Vanilla JavaScript (sin frameworks pesados)

## 🔧 Desarrollo

### Reinstalar Base de Datos

```bash
rm data/finances.db
python backend/init_db.py
```

### Ejecutar en Modo Debug

```bash
python run.py
```

El servidor se recargará automáticamente al detectar cambios en el código.

### Actualizar Tasa de Cambio

Puedes actualizar las tasas de cambio mediante la API o directamente en `config.py`.

## 📝 Próximas Características (Roadmap)

- [ ] Módulo de hipoteca con simulador
- [ ] Reportes avanzados con más gráficos
- [ ] Exportar datos a CSV/Excel
- [ ] Metas de ahorro
- [ ] Transacciones recurrentes automáticas
- [ ] Categorías personalizables
- [ ] Multi-usuario con autenticación

## 🐛 Troubleshooting

**Error: "No module named backend"**
- Asegúrate de ejecutar desde la raíz del proyecto
- Verifica que todas las dependencias estén instaladas

**Error: "Database is locked"**
- Cierra otras conexiones a la base de datos
- Reinicia la aplicación

**Importador YNAB no funciona**
- Verifica que el CSV tenga las columnas correctas
- Revisa los errores en la página de importación
- Las fechas con formato "########" serán omitidas

## 📄 Licencia

Este proyecto es de uso personal.

## 👨‍💻 Autor

Creado con ❤️ para gestionar finanzas personales de forma simple y efectiva.