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

### API Endpoints disponibles:

**Crear grupo:**
```bash
POST /api/categories/groups
{
  "name": "Mi Nuevo Grupo",
  "is_income": false
}
```

**Eliminar grupo:**
```bash
DELETE /api/categories/groups/{id}?force=true
```

**Frontend**: Pendiente agregar UI (botones en budget.html)

---

## 3. ⚠️ No puedo seleccionar categoría en transacciones

### Diagnóstico:
El código JavaScript está correcto. El problema puede ser:

1. **No hay categorías en la base de datos**
   ```bash
   # Verificar
   curl http://localhost:8000/api/categories/groups
   ```

2. **Todas las categorías están ocultas (`is_hidden=true`)**

### Solución:
```bash
# Reinicializar con datos de ejemplo
python init_db.py
```

Esto creará categorías predeterminadas.

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

## 6. ⚠️ No puedo modificar "dinero que tengo hoy" en Savings

### Estado: **NECESITA CLARIFICACIÓN**

**Pregunta:** ¿Te refieres a:
- A) El monto inicial (`initial_amount`) de una categoría de ahorro?
- B) El balance actual de una cuenta?

**Si es A (categoría de ahorro):**
Necesito agregar un endpoint PATCH para actualizar `initial_amount`.

**Si es B (cuenta):**
Ya existe: Ir a "Cuentas" → Editar cuenta → Cambiar balance

---

## 7. ⚠️ Reportes: USD no aparece en gastos COP

### Estado: **POR CORREGIR**

El problema es que los reportes filtran por moneda exacta.

### Necesito agregar:
- Conversión automática a la moneda seleccionada
- Usar exchange rates para convertir
- Mostrar total combinado

---

## 8. ⚠️ No puedo seleccionar categoría en transacciones recurrentes

### Mismo problema que #3

Solución: Ejecutar `python init_db.py` para crear categorías.

---

## 📋 Resumen de Estado

| Problema | Estado | Acción Requerida |
|----------|--------|------------------|
| Error BD initial_amount | ✅ Resuelto | `python migrate_db.py` |
| Agregar/Eliminar grupos | ✅ API lista | Agregar UI frontend |
| Selector de categorías | ⚠️ Datos | `python init_db.py` |
| Hipoteca pago extra | 🔧 Por corregir | - |
| Hipoteca fecha/total | 🔧 Por corregir | - |
| Editar monto inicial savings | ❓ Clarificar | ¿Qué quieres editar? |
| Reportes multi-moneda | 🔧 Por corregir | - |
| Categorías en recurrentes | ⚠️ Datos | `python init_db.py` |

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
