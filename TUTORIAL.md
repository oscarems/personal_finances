# 📚 Tutorial - Personal Finances (YNAB-style)

**Sistema de finanzas personales multi-moneda basado en la metodología YNAB**

---

## 📖 Tabla de Contenidos

1. [Introducción](#introducción)
2. [Primeros Pasos](#primeros-pasos)
3. [Conceptos Clave](#conceptos-clave)
4. [Cuentas](#cuentas)
5. [Presupuesto](#presupuesto)
6. [Transacciones](#transacciones)
7. [Transferencias](#transferencias)
8. [Reportes](#reportes)
9. [Importar desde YNAB](#importar-desde-ynab)
10. [Transacciones Recurrentes](#transacciones-recurrentes)
11. [Multi-Moneda](#multi-moneda)
12. [Tips y Mejores Prácticas](#tips-y-mejores-prácticas)

---

## Introducción

Este sistema implementa la metodología YNAB (You Need A Budget) con soporte multi-moneda (COP/USD). La filosofía es simple:

**"Dale un propósito a cada peso"**

En lugar de mirar hacia atrás preguntándote "¿En qué gasté?", miras hacia adelante: "¿Qué necesito que este dinero haga antes de recibir más?"

---

## Primeros Pasos

### 1. Iniciar el Sistema

```bash
# Instalar dependencias
pip install -r requirements.txt

# Inicializar base de datos
python backend/init_db.py

# Iniciar servidor
python run.py
```

El servidor estará disponible en `http://localhost:8000`

### 2. Primer Login

La aplicación abre directamente (sin autenticación por ahora). Verás:
- Dashboard con resumen
- Sidebar con navegación

---

## Conceptos Clave

### 1. **Ready to Assign (Disponible para Asignar)**
Es el dinero que tienes en tus cuentas pero que **NO** tiene un propósito asignado todavía.

**Fórmula:**
```
Ready to Assign = Total en Cuentas - Total Asignado en Presupuesto
```

**Objetivo:** Llevar esto a $0 asignando cada peso a una categoría.

### 2. **Categorías con Rollover**
Hay dos tipos:

**🔁 Reset (Reiniciar):**
- Lo no gastado vuelve a "Ready to Assign" el próximo mes
- Usa esto para gastos mensuales regulares (mercado, servicios)

**🔄 Accumulate (Acumular):**
- Lo no gastado se queda en la categoría
- Usa esto para ahorros y metas (vacaciones, emergencias)

### 3. **Four Rules of YNAB**

1. **Give Every Dollar a Job**: Asigna cada peso a una categoría
2. **Embrace Your True Expenses**: Planea para gastos irregulares
3. **Roll With The Punches**: Ajusta tu presupuesto cuando cambien las cosas
4. **Age Your Money**: Trata de vivir con dinero del mes pasado

---

## Cuentas

### Tipos de Cuenta Soportados

| Tipo | Descripción | Campos Especiales |
|------|-------------|-------------------|
| 💳 Corriente | Cuenta bancaria diaria | - |
| 🏦 Ahorros | Cuenta de ahorros | Tasa de interés |
| 💳 Tarjeta Crédito | Tarjeta de crédito | Cupo, día de pago |
| 💰 Crédito Libre | Crédito personal | Tasa, cuota mensual, monto original |
| 🏠 Hipoteca | Préstamo hipotecario | Tasa, cuota mensual, monto original |
| 📜 CDT | Certificado depósito | Tasa, fecha vencimiento, monto original |
| 📈 Inversión | Cuenta de inversiones | - |
| 💵 Efectivo | Dinero en efectivo | - |

### Crear una Cuenta

1. Ve a **"Cuentas"**
2. Click **"+ Nueva Cuenta"**
3. Completa:
   - **Nombre**: Ej. "Davivienda Corriente"
   - **Tipo**: Selecciona de la lista
   - **Moneda**: COP o USD
   - **Saldo Inicial**: Balance actual de la cuenta
   - **Campos opcionales**: Según el tipo de cuenta
4. Click **"Guardar"**

**Importante:**
- Cada cuenta tiene **una sola moneda oficial**
- Verás la conversión a la otra moneda automáticamente
- Marca "Incluir en presupuesto" para cuentas normales
- Desmarca para cuentas de seguimiento (inversiones, hipotecas)

### Vista de Cuentas

Verás tarjetas con:
- Nombre y tipo
- Saldo en moneda oficial (grande)
- Conversión a otra moneda (pequeño)
- Ícono según tipo

---

## Presupuesto

### Estructura

**Grupos de Categorías** → **Categorías**

Ejemplo:
```
📌 Needs (Grupo)
   ├─ Gym (Categoría)
   ├─ Cosméticos
   └─ Transporte

🏠 Hogar (Grupo)
   ├─ Arriendo
   ├─ Mercado
   └─ Servicios
```

### Asignar Dinero

1. Ve a **"Presupuesto"**
2. Mira tu **"Disponible para Asignar"** (arriba)
3. Click en una categoría
4. Ingresa el monto a asignar
5. Click **"Asignar"**

### Columnas del Presupuesto

| Columna | Significado |
|---------|-------------|
| **Asignado** | Dinero que planeaste usar |
| **Gastado** | Dinero realmente gastado |
| **Disponible** | Lo que te queda (Asignado - Gastado) |

**Barra de progreso:**
- 🟢 Verde: < 80% gastado
- 🟡 Amarillo: 80-100% gastado
- 🔴 Rojo: > 100% gastado (sobregiro!)

### Selector de Moneda

Arriba a la derecha puedes cambiar entre COP y USD:
- **NO separa los presupuestos**
- Solo cambia cómo **visualizas** los montos
- Suma asignaciones de ambas monedas convertidas

**Ejemplo:**
Si asignas:
- $100 USD a "Mercado"
- $400,000 COP a "Mercado"

Al ver en COP verás: **$800,000 COP** (suma convertida)

---

## Transacciones

### Crear Transacción

1. Ve a **"Transacciones"**
2. Click **"+ Nueva Transacción"**
3. Completa:
   - **Fecha**: Fecha de la transacción
   - **Cuenta**: De qué cuenta sale/entra
   - **Beneficiario**: Ej. "Éxito", "Mi Empleador"
   - **Categoría**: A qué categoría pertenece
   - **Monto**:
     - Positivo = Ingreso
     - Negativo = Gasto
   - **Moneda**: COP o USD
   - **Memo**: Notas opcionales
4. Check **"✓ Transacción reconciliada"** si ya confirmaste con banco
5. Click **"Guardar"**

### Tipos de Transacciones

**💰 Ingreso (monto positivo):**
```
Cuenta: Davivienda Corriente
Beneficiario: Mi Empleador
Categoría: Salario (categoría Income)
Monto: +5000000 COP
```

**💸 Gasto (monto negativo):**
```
Cuenta: Davivienda Corriente
Beneficiario: Éxito
Categoría: Mercado
Monto: -150000 COP
```

### Filtros

Usa los filtros arriba para:
- Ver solo transacciones de una cuenta
- Ver solo de una categoría
- Limitar cantidad mostrada

---

## Transferencias

### ¿Cuándo usar Transferencias?

Cuando mueves dinero **entre tus propias cuentas**:
- Ahorros → Corriente
- USD → COP
- Efectivo → Banco

**NO uses transferencias para:**
- Pagos a terceros
- Compras
- Ingresos

### Crear Transferencia

1. Ve a **"Transacciones"**
2. Click **"⇄ Nueva Transferencia"**
3. Completa:
   - **Fecha**: Fecha de la transferencia
   - **Desde**: Cuenta origen (fondo rojo)
   - **Moneda origen**: COP o USD
   - **Hacia**: Cuenta destino (fondo verde)
   - **Moneda destino**: COP o USD
   - **Monto**: Cantidad a transferir (en moneda origen)
   - **Memo**: Opcional
4. Click **"Crear Transferencia"**

**Magia automática:**
- Crea 2 transacciones vinculadas:
  - Salida (-) de cuenta origen
  - Entrada (+) en cuenta destino
- Si las monedas son diferentes, **convierte automáticamente**
- Al eliminar una, elimina ambas

**Ejemplo:**
```
Desde: Ahorros USD ($100 USD)
Hacia: Corriente COP
Resultado:
  - Ahorros USD: -$100 USD
  - Corriente COP: +$400,000 COP (con tasa 4000)
```

---

## Reportes

### Tipos de Reportes

1. **Expenses by Category** (Gastos por Categoría)
   - Pie chart de tus gastos
   - Filtra por fecha y categoría

2. **Income vs Expenses** (Ingresos vs Gastos)
   - Comparación mensual
   - Filtra por rango de fechas

3. **Spending Trends** (Tendencias de Gasto)
   - Ver cómo cambian tus gastos en el tiempo

### Generar Reporte

1. Ve a **"Reportes"**
2. Selecciona tipo de reporte
3. Ajusta filtros (fechas, categorías)
4. Click **"Generar Reporte"**

---

## Importar desde YNAB

### Exportar desde YNAB

1. En YNAB web, ve a tu presupuesto
2. Click en el nombre del presupuesto (arriba izquierda)
3. **"Export Budget Data"**
4. Selecciona **"Register"** (todas las transacciones)
5. Descarga el CSV

### Importar

1. En nuestra app, ve a **"Importar"** (o `/import`)
2. Click **"Seleccionar archivo"**
3. Elige el CSV de YNAB
4. Click **"Importar"**

**El sistema:**
- Crea payees automáticamente
- Asocia categorías por nombre
- Asocia cuentas por nombre
- Parsea fechas en formato DD/MM/YYYY
- Muestra resumen de éxito/errores

---

## Transacciones Recurrentes

### Crear Recurrencia

1. Ve a `/recurring` (no hay link en menú aún)
2. Click **"+ Nueva Recurrencia"**
3. Completa:
   - Cuenta, beneficiario, categoría
   - Monto y moneda
   - **Frecuencia**:
     - Daily (diaria)
     - Weekly (semanal)
     - Monthly (mensual)
     - Yearly (anual)
   - **Fecha inicio**: Cuándo empieza
   - **Fecha fin**: Opcional, cuándo termina

### Generar Transacciones

Las transacciones recurrentes se generan automáticamente:
- El sistema revisa diariamente
- Crea transacciones hasta hoy
- Puedes forzar generación desde `/recurring`

**Ejemplo:**
```
Arriendo mensual:
- Monto: -1,500,000 COP
- Frecuencia: Monthly
- Inicio: 01/01/2024
- Día: 1 (cada mes el día 1)
```

---

## Multi-Moneda

### Características

**✅ Lo que el sistema hace:**
- Cada cuenta tiene **1 moneda oficial**
- Muestra conversión a la otra moneda en todas partes
- Presupuesto unificado (suma ambas monedas)
- Transferencias con conversión automática
- Tasa de cambio real desde API (con fallbacks)

**🔍 Conversiones:**
- API primaria (exchangerate-api.com)
- API fallback (exchangerate.host)
- Promedio últimos 5 días
- Default: 4000 COP por USD

### Presupuesto Multi-Moneda

**Cómo funciona:**

1. Puedes asignar dinero en cualquier moneda a cualquier categoría
2. El sistema suma todo convertido a la moneda que estés viendo
3. "Ready to Assign" considera **todas** tus cuentas

**Ejemplo:**
Tienes:
- $500 USD en banco
- $2,000,000 COP en banco

Presupuesto en COP muestra:
- Ready to Assign: $4,000,000 COP
  (= $2,000,000 + $500 × 4000)

---

## Tips y Mejores Prácticas

### 1. **Empieza Simple**

No necesitas todas las categorías el primer día:
```
✅ Empieza con:
   - Mercado
   - Transporte
   - Servicios
   - Otros

❌ Evita:
   - 50 categorías ultra-específicas
```

### 2. **Budget Before You Get Paid**

Cuando sepas cuánto vas a recibir:
1. Registra el ingreso (positivo)
2. Asigna ese dinero a categorías
3. Lleva "Ready to Assign" a $0

### 3. **Use Memos**

Los memos son útiles para:
- Recordar qué era esa transacción
- Detalles (ej: "Compra silla oficina")
- Número de factura

### 4. **Reconcilia Regularmente**

Cada semana:
1. Compara tus transacciones con el banco
2. Marca como reconciliadas (✓)
3. Corrige diferencias

### 5. **Categorías Accumulate para Metas**

Usa **"accumulate"** para:
- Fondo de emergencia
- Vacaciones
- Regalos navideños
- Seguro anual

El dinero se acumula mes a mes.

### 6. **No Temas Mover Dinero**

Si gastaste de más en "Mercado":
1. Mueve dinero de otra categoría
2. Ajusta el presupuesto
3. No te sientas mal - es normal!

**Regla de Oro:** Nunca gastes sin cubrir en el presupuesto.

### 7. **Transferencias entre Monedas**

Para cambiar USD a COP:
```
Transferencia:
  Desde: Cuenta USD
  Hacia: Cuenta COP
  Monto: 100 USD

Automáticamente convierte a COP
```

### 8. **Presupuesto en Tu Moneda Principal**

Si gastas principalmente en COP:
- Ve el presupuesto en COP
- Verás conversiones pequeñas de USD

Si gastas en ambas:
- Alterna entre vistas
- El presupuesto es el mismo, solo cambia la visualización

---

## Arquitectura del Sistema

### Backend (FastAPI + SQLAlchemy)

```
backend/
├── models/          # Modelos de base de datos
├── services/        # Lógica de negocio
├── api/            # Endpoints REST
└── utils/          # Utilidades (importers, etc.)
```

### Frontend (HTML + Vanilla JS)

```
frontend/
└── templates/      # Páginas HTML con Tailwind CSS
```

### Base de Datos (SQLite)

Tablas principales:
- `accounts` - Cuentas
- `transactions` - Transacciones
- `categories` / `category_groups` - Categorías
- `budget_months` - Asignaciones presupuestarias
- `exchange_rates` - Tasas históricas
- `recurring_transactions` - Recurrencias

---

## Troubleshooting

### "no such column" error

**Problema:** Base de datos desactualizada

**Solución:**
```bash
# CUIDADO: Borra todos los datos
del data/finances.db  # Windows
rm data/finances.db   # Linux/Mac

python backend/init_db.py
```

### Gráficos no cargan

**Problema:** Chart.js no cargó

**Solución:**
- Revisa conexión a internet
- Abre consola del navegador (F12) y mira errores

### Tasa de cambio incorrecta

**Problema:** API no responde

**Solución:** El sistema usa fallbacks automáticos:
1. API principal
2. API secundaria
3. Promedio últimos 5 días
4. Default 4000

Si quieres forzar actualización, reinicia el servidor.

### Transacciones duplicadas en importación

**Problema:** Importaste dos veces

**Solución:**
- Borra las duplicadas manualmente
- O resetea la base de datos y vuelve a importar

---

## Próximas Funcionalidades

**En roadmap:**
- [ ] Dashboard con gráficos reales
- [ ] Búsqueda avanzada de transacciones
- [ ] Split transactions (dividir transacciones)
- [ ] Goals/Metas con tracking
- [ ] Age of Money
- [ ] Mobile app (PWA)
- [ ] Autenticación multi-usuario
- [ ] Backup automático
- [ ] Exportar a Excel/CSV

---

## Soporte

**Encontraste un bug?**
- Abre un issue en GitHub

**Preguntas?**
- Lee este tutorial
- Revisa la documentación de YNAB (metodología similar)

---

## Créditos

**Metodología:** Basado en YNAB (You Need A Budget)
**Stack:** FastAPI, SQLAlchemy, SQLite, Tailwind CSS
**Desarrollado por:** [Tu nombre/organización]

---

## Licencia

[Tu licencia aquí]

---

**¡Feliz presupuesto! 💰**

Recuerda: El objetivo no es restringir, sino **dar propósito** a tu dinero.
