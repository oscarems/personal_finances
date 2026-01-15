# 🔧 Problemas Reportados y Soluciones

## 1. ❌ Error: `no such column: categories.initial_amount`

### Solución INMEDIATA:
```bash
python migrate_db.py
```

Este script agrega la columna faltante sin perder datos.

**Alternativa (empezar de cero):**
```powershell
Remove-Item data\finances.db
python init_db.py
```

---

## 2. ✅ RESUELTO: Agregar/Eliminar Grupos de Presupuesto

### Solución Implementada:

Ya puedes gestionar grupos desde la interfaz de presupuesto:

**Cómo crear grupo:**
1. Ir a Presupuesto
2. Click en botón **"+ Nuevo Grupo"** (esquina superior derecha)
3. Ingresar nombre del grupo
4. Seleccionar tipo: Gastos o Ingresos
5. Click "Crear Grupo"

**Cómo eliminar grupo:**
1. Click en el icono de **basura** (🗑️) junto al nombre del grupo
2. Confirmar la eliminación
3. **ADVERTENCIA:** Esto eliminará también todas las categorías del grupo

**Ubicación en código:**
- Frontend: `frontend/templates/budget.html`
  - Botón "Nuevo Grupo": líneas 13-15
  - Modal de creación: líneas 157-184
  - Botón eliminar: líneas 339-345
  - Funciones JS: líneas 255-289, 644-678
- Backend: `backend/api/categories.py`
  - POST `/api/categories/groups`: líneas 87-115
  - DELETE `/api/categories/groups/{id}`: líneas 118-148

---

## 3. ✅ RESUELTO: No puedo seleccionar categoría en transacciones

### Solución Implementada:

Ahora hay **múltiples formas** de resolver este problema:

#### Opción 1: Desde la Interfaz (Recomendado)
1. Ir a **Transacciones**
2. Si no hay categorías, verás un banner amarillo con advertencia
3. Click en **"📦 Crear Categorías Predeterminadas"**
4. Confirmar y listo!

#### Opción 2: Desde Terminal
```bash
# Script específico para categorías (seguro, no afecta otros datos)
python seed_categories.py

# O usando init_db (también seguro, solo agrega si no existen)
python init_db.py
```

#### Opción 3: Crear Manualmente
- Ir a **Presupuesto** → Click "**+ Nuevo Grupo**" → Agregar categorías

**Ubicación en código:**
- Script: `seed_categories.py`
- Endpoint API: POST `/api/categories/seed` (líneas 327-426 en `backend/api/categories.py`)
- Banner UI: `frontend/templates/transactions.html` (líneas 21-49)
- Función JS: `seedCategories()` (líneas 626-654)

---

## 4. ⚠️ Hipoteca: Pago extra no recalcula gráficas

### Estado: **POR CORREGIR**

Necesito agregar:
- Evento `onchange` en el input de pago extra
- Recalculo automático al cambiar valor
- Fecha de finalización
- Total a pagar

### Workaround temporal:
Después de modificar el pago extra, haz clic en "Calcular" nuevamente.

---

## 5. ⚠️ No sale fecha de finalización ni total a pagar en hipoteca

### Estado: **POR CORREGIR**

Los datos están en el response pero no se muestran en el HTML.

Necesito agregar:
```html
<div>Fecha de finalización: <span id="endDate"></span></div>
<div>Total a pagar: <span id="totalToPay"></span></div>
```

---

## 6. ✅ RESUELTO: No puedo modificar "dinero que tengo hoy" en Savings

### Solución Implementada:

Se agregó un campo **"Dinero que Tengo Hoy (Inicial)"** en el modal de asignación de presupuesto:

**Cómo usar:**
1. Ir a Presupuesto
2. Click en una categoría de tipo "Meta/Ahorro" (accumulate)
3. El campo "💎 Dinero que Tengo Hoy (Inicial)" aparecerá automáticamente
4. Ingresar el monto que ya tienes ahorrado para esa categoría
5. Click "Guardar Presupuesto"

**Ubicación en código:**
- Frontend: `frontend/templates/budget.html` líneas 71-84
- Backend: Usa endpoint PATCH `/api/categories/{id}` (líneas 203-255 en `backend/api/categories.py`)

---

## 7. ✅ RESUELTO: Reportes: USD no aparece en gastos COP

### Solución Implementada:

Los reportes ahora **incluyen TODAS las monedas** con conversión automática:

**Qué cambió:**
- Todos los reportes ahora muestran transacciones en COP y USD combinadas
- Se usa el exchange rate actual para convertir a la moneda seleccionada
- Aplica a todos los endpoints de reportes:
  - `/api/reports/spending-by-category`
  - `/api/reports/spending-by-group`
  - `/api/reports/income-vs-expenses`
  - `/api/reports/spending-trends`
  - `/api/reports/summary`

**Ejemplo:**
- Si seleccionas "Ver en COP", verás gastos en COP + gastos en USD convertidos a COP
- Si seleccionas "Ver en USD", verás gastos en USD + gastos en COP convertidos a USD

**Ubicación en código:**
- Backend: `backend/api/reports.py` - Funciones helper `get_exchange_rate()` y `convert_to_currency()` (líneas 17-46)
- Todas las funciones de reporte modificadas para incluir conversión

---

## 8. ✅ RESUELTO: No puedo seleccionar categoría en transacciones recurrentes

### Mismo problema que #3

**Solución:** Ver solución del problema #3 arriba. Las tres opciones funcionan igual:
1. Desde la UI en Transacciones (botón "Crear Categorías Predeterminadas")
2. Desde terminal con `python seed_categories.py` o `python init_db.py`
3. Crear manualmente desde Presupuesto

---

## 📋 Resumen de Estado

| Problema | Estado | Acción Requerida |
|----------|--------|------------------|
| Error BD initial_amount | ✅ Resuelto | `python migrate_db.py` |
| Agregar/Eliminar grupos | ✅ Resuelto | Botón "Nuevo Grupo" en presupuesto |
| Selector de categorías | ✅ Resuelto | Banner + botón en Transacciones |
| Hipoteca pago extra | 🔧 Por corregir | - |
| Hipoteca fecha/total | 🔧 Por corregir | - |
| Editar monto inicial savings | ✅ Resuelto | Ver campo en modal presupuesto |
| Reportes multi-moneda | ✅ Resuelto | Conversión automática implementada |
| Categorías en recurrentes | ✅ Resuelto | Mismo que selector de categorías |

---

## 🚀 Acción Inmediata Recomendada

### Paso 1: Actualizar base de datos
```bash
python migrate_db.py
```

### Paso 2: Verificar categorías
```bash
curl http://localhost:8000/api/categories/groups
```

Si retorna array vacío `[]`:

### Paso 3: Inicializar con datos
```bash
python init_db.py
```

### Paso 4: Iniciar servidor
```bash
python run.py
```

---

## ⏭️ Próximos Pasos

¿Qué quieres que corrija primero?

1. Mejorar simulador de hipoteca (fecha finalización + recalculo auto)
2. Reportes multi-moneda
3. UI para gestionar grupos de presupuesto
4. Clarificar problema de "dinero que tengo hoy"

**Déjame saber tu prioridad y continúo corrigiendo.** 🎯
