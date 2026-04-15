# Corrección del problema: 45 USD se muestran como 90 USD

## 🔴 Problema Identificado

Tu categoría de ahorros con **initial_amount = 45 USD** se estaba mostrando como **90 USD** en el disponible.

### Causa Raíz

El problema ocurría cuando:
1. Tienes una categoría de savings con `initial_amount` (ej: 45 USD)
2. **NO especificaste la moneda inicial** (`initial_currency_id` = NULL)
3. Creaste presupuestos en **múltiples monedas** (USD y COP)

El código aplicaba los 45 USD a **AMBAS monedas**:
- Presupuesto USD: +45 USD
- Presupuesto COP: +45 USD convertidos a COP (~180,000 COP)
- Al ver en USD: 45 + 45 = **90 USD** ❌

## ✅ Solución Implementada

He corregido el código para que el `initial_amount` **solo se aplique a la moneda especificada** en `initial_currency_id`.

**Ahora el código requiere que especifiques la moneda inicial para evitar duplicación.**

## 🔧 Pasos para Corregir tus Datos

### Opción 1: Usar el Script Automático (Recomendado)

```bash
# Paso 1: Actualizar las categorías sin moneda inicial
python src/finance_app/scripts/fix_missing_initial_currency.py

# Paso 2: Recalcular todos los presupuestos de savings
python src/finance_app/scripts/fix_savings_double_count.py
```

El primer script:
- Identifica categorías con `initial_amount` pero sin `initial_currency_id`
- Usa heurística: montos < 10,000 → USD, montos >= 10,000 → COP
- Te pide confirmación antes de aplicar cambios

El segundo script:
- Recalcula todos los presupuestos de categorías de savings
- Aplica la lógica corregida
- Elimina la duplicación

### Opción 2: Actualizar Manualmente desde la UI

1. Ve a la página de presupuesto
2. Para cada categoría de savings:
   - Haz clic en el botón de editar (⚙️)
   - En el campo "Moneda inicial", selecciona la moneda correcta (USD o COP)
   - Guarda los cambios
3. Recarga la página para ver los valores corregidos

## 📊 Resultado Esperado

Después de aplicar la corrección:

**ANTES:**
```
Categoría: Ahorros
Initial Amount: 45 USD (sin moneda especificada)
Disponible: 90 USD ❌ (duplicado)
```

**DESPUÉS:**
```
Categoría: Ahorros
Initial Amount: 45 USD
Initial Currency: USD ✓
Disponible: 45 USD ✓ (correcto)
```

## 🎯 Prevención Futura

A partir de ahora:
- Cuando crees una categoría de savings con "Dinero que tengo hoy"
- **SIEMPRE especifica la moneda inicial** (USD o COP)
- Esto previene la duplicación automáticamente

## 📝 Archivos Modificados

- `src/finance_app/services/budget_service.py`: Corregida lógica de `calculate_available()`
- `src/finance_app/scripts/fix_missing_initial_currency.py`: Script para actualizar categorías
- `src/finance_app/scripts/fix_savings_double_count.py`: Script para recalcular presupuestos
- `src/finance_app/scripts/debug_45_usd.py`: Script de debugging para análisis

## 🚀 Git

Cambios pushed al branch: `claude/fix-savings-duplication-ZUAD2`
- Commit: `570b263` - "Fix critical bug: initial_amount applied to ALL currencies..."

¿Necesitas ayuda ejecutando los scripts o tienes preguntas? ¡Avísame!
