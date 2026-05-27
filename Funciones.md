# Funciones del Proyecto

Estado de cada función: ✅ Implementado | ⚠️ Parcial | ❌ Pendiente | 🗑️ Eliminado

---

## 1. Presupuesto ✅

- ✅ Múltiples grupos y categorías de presupuesto
- ✅ Cada categoría puede estar en COP o USD
- ✅ Frontend muestra asignado, gastado, disponible y uso en ambas monedas
- ✅ Desde el frontend se pueden modificar valores asignados y moneda (el modal preselecciona la moneda activa)
- ✅ Los valores asignados solo pueden ser de una moneda a la vez
- ✅ Categorías de ahorro: el disponible se acumula mes a mes (rollover)
- ✅ Categorías de gasto: se reinician mes a mes
- ✅ Eliminar categorías (con confirmación y doble confirmación si tiene datos asociados)
- ✅ Cascada de valores asignados a meses futuros (no sobreescritos)
- ✅ Inicializar mes desde plantilla

---

## 2. Cuentas ✅

- ✅ Tipos: Ahorros, Tarjeta de crédito, Hipoteca, Préstamos
- ✅ Moneda por cuenta (COP o USD)
- ✅ Nombre, institución, saldo actual, notas
- ✅ Deudas vinculadas a categoría de presupuesto para pago mensual

---

## 3. Transacciones ⚠️

- ✅ Ingesta manual desde la UI (fecha, monto, cuenta, categoría)
- ✅ Transferencias entre cuentas
- ✅ Ajuste de saldo
- ❌ **Importar desde Gmail con Ollama** — ver sección 3.1

### 3.1 Importar Gmail con Ollama ❌

**Flujo deseado:**
1. El usuario abre la pantalla "Importar Gmail"
2. La app consulta Gmail vía IMAP (usando `web_scrapping_email.py` ya existente) y trae los correos nuevos desde la última importación
3. Se muestra una lista de correos pendientes de procesar (uno a uno)
4. Para cada correo, el usuario hace click en "Procesar" y el backend llama a Ollama local para extraer: fecha, cuenta, monto, categoría
5. El usuario puede editar los campos extraídos antes de confirmar
6. Al confirmar, se crea la transacción y el correo se marca como procesado

**Instrucciones para implementar:**

**Backend:**
- Archivo: `src/finance_app/api/gmail_import.py` — reemplazar contenido completamente
- Nuevo endpoint `GET /api/import/gmail/emails` → llama a `fetch_emails_preview()` del script existente, retorna lista de correos sin procesar (id, asunto, fecha, preview del cuerpo). Guardar en DB cuáles ya fueron procesados (tabla `gmail_processed` con campo `message_id`).
- Nuevo endpoint `POST /api/import/gmail/process/{message_id}` → toma el cuerpo del correo, lo envía a Ollama (modelo configurable, por defecto `llama3`) via `http://localhost:11434/api/generate`, pide que extraiga JSON con campos `{fecha, monto, moneda, cuenta, descripcion, categoria_sugerida}`. Retorna el JSON extraído.
- Nuevo endpoint `POST /api/import/gmail/confirm` → recibe los campos confirmados por el usuario, crea la transacción y marca el `message_id` como procesado.
- El prompt para Ollama debe ir en `src/finance_app/services/gmail_ollama_service.py`. Incluir en el prompt la lista de cuentas y categorías disponibles para que Ollama pueda sugerir.
- Modelo de DB: agregar tabla `gmail_processed_messages (id, message_id TEXT UNIQUE, processed_at DATETIME, transaction_id INT NULL)` — usar el patrón de migración existente en `database.py`.

**Frontend:**
- Archivo: `src/finance_app/static/js/pages/gmail-import.js` — reemplazar contenido completamente
- La pantalla tiene dos secciones:
  1. **Panel izquierdo** — lista de correos pendientes (asunto, fecha, preview). Botón "Sincronizar" llama al script IMAP.
  2. **Panel derecho** — formulario de confirmación que aparece al seleccionar un correo. Muestra los campos extraídos por Ollama (editables) + botón "Confirmar" y "Omitir".
- Estado de carga mientras Ollama procesa (puede tardar 5-15s).
- Si Ollama falla, permitir ingreso manual de los campos.
- Ruta ya registrada: `/advanced/gmail` en `app.js`.

---

## 4. Transacciones Recurrentes ✅

- ✅ Crear, editar, eliminar transacciones recurrentes
- ✅ Tipos: ingreso, egreso, transferencia
- ✅ Frecuencia configurable
- ✅ Generación manual desde la UI ("Generar pendientes")

---

## 5. Simuladores ✅

### 5.1 Fondo de Emergencia ✅
- ✅ Seleccionar categorías de gasto como "esenciales"
- ✅ Seleccionar categorías de ahorro como "fondo de emergencia"
- ✅ Calcula meses cubiertos = total_ahorros / gasto_mensual_esencial
- ✅ Ajuste sin afectar datos reales

### 5.2 Hipoteca / Deuda ✅
- ✅ Ver saldo actual, tasa de interés, cuota mínima
- ✅ Simular escenarios de pago anticipado (abono a capital)
- ✅ Método avalancha y bola de nieve
- ✅ Proyección gráfica de saldo en el tiempo (amortización)

---

## 6. Dashboard ✅

- ✅ Resumen de cuentas con saldo total
- ✅ Presupuesto del mes (gastado vs asignado)
- ✅ Últimas transacciones
- ✅ Patrimonio neto, total activos, total deudas

---

## 7. Análisis y Reportes ✅

- ✅ Reportes de gastos por categoría y período
- ✅ Reportes de ingresos
- ✅ Reporte de deuda
- ✅ Salud financiera (score con indicadores)
- ✅ Patrimonio y activos (bienes, inversiones, etc.)

---

## 8. Metas de Ahorro ✅

- ✅ Crear metas con nombre, monto objetivo, fecha
- ✅ Registrar contribuciones
- ✅ Ver progreso por meta

---

## 9. Funciones eliminadas 🗑️

Las siguientes funciones existen en el backend (API + archivos JS) pero fueron removidas del sidebar y la navegación. Los archivos pueden eliminarse en una limpieza futura si se confirma que no se necesitan.

| Función | Archivos |
|---|---|
| Reglas de Email | `api/email_sender_rules.py`, `pages/email-rules.js` |
| Chat SQL | `api/chat.py`, `pages/chat.js` |
| Gmail Import (vieja implementación) | `api/gmail_import.py` (reemplazar con nueva implementación — ver 3.1), `pages/gmail-import.js` |

---

## 10. Limpieza pendiente ❌

**Instrucciones para Claude Code:**

- Eliminar los archivos `src/finance_app/static/js/pages/email-rules.js` y `src/finance_app/static/js/pages/chat.js` (ya no están en las rutas del router).
- Eliminar o deshabilitar los routers `api/email_sender_rules.py` y `api/chat.py` en `src/finance_app/app.py` (quitar los `include_router` correspondientes).
- El archivo `api/gmail_import.py` no debe eliminarse — debe reemplazarse con la nueva implementación descrita en la sección 3.1.
- Verificar que al eliminar estos routers no se rompa ningún import en `app.py`.
