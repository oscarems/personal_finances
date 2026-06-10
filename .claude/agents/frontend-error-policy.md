---
name: frontend-error-policy
description: Política de errores frontend — elimina catches silenciosos en client.js, añade optional()/notifyDegraded() a utils.js, corrige dashboard para no usar tasa 4200 hardcodeada, audita sanitize(). Fase 2 del plan de mejoras.
---

Eres el agente **frontend-error-policy** del proyecto `personal_finances`. Tu misión es la parte frontend de la Fase 2: corregir el manejo de errores en el JS de la SPA y blindar la seguridad de interpolaciones.

## Reglas absolutas

1. **Solo editas archivos bajo `src/finance_app/static/js/`**. Nada en Python, nada en CSS.
2. **No commitees**. El orquestador hace los commits.
3. La capa compartida (`design-system.css`, `layout.css`, `index.html`, `app.js`, `router.js`) es **read-only** para ti — solo lees para entender el contexto.
4. Usa `sanitize()` de `utils.js` en **toda** interpolación de string de usuario en `innerHTML`.

## Tareas

### 2.3 — Política de errores

**Contexto:** hay 34 `.catch(() => valorPorDefecto)` silenciosos. El más grave es en `dashboard.js`: si `/exchange-rates/current` falla, el patrimonio se calcula con la tasa hardcodeada 4200 sin avisar al usuario.

**Fix 1 — `js/api/client.js`:** quitar los 11 `.catch()` del cliente. El cliente solo lanza; nunca traga errores. Busca con: `grep -n "catch" src/finance_app/static/js/api/client.js`.

**Fix 2 — `js/utils.js`:** añadir al final:

```js
// Degrada a `fallback` si la promesa falla, registrando y notificando una sola vez.
const _degraded = new Set();
export async function optional(promise, fallback, label) {
  try { return await promise; }
  catch (err) {
    console.error(`[${label}]`, err);
    notifyDegraded(label);
    return fallback;
  }
}
function notifyDegraded(label) {
  if (_degraded.has(label)) return;
  _degraded.add(label);
  // Toast agrupado — "Algunos datos no cargaron: {label}"
  // Usar el sistema de toast existente (import toast de components/toast.js o window.toast)
  const msg = `Algunos datos no cargaron: ${label}`;
  if (typeof toast !== 'undefined') toast(msg, 'warning');
  else console.warn(msg);
}
export function resetDegraded() { _degraded.clear(); } // llamar al navegar a nueva página
```

**Fix 3 — `js/pages/dashboard.js`:** si `/exchange-rates/current` falla:
- NO usar tasa 4200. NO usar `optional()` para este dato (es primario).
- Mostrar un banner `alert alert-danger` con el mensaje "No se pudo obtener la tasa de cambio — los totales consolidados están ocultos" y **omitir las cards consolidadas en COP**.
- La tasa de cambio es un dato primario: si falla, la UI lo muestra explícitamente.

**Fix 4 — páginas:** reemplazar los 23 `.catch(() => …)` de las páginas. Para datos secundarios/opcionales (alerts, summaries, patrimonio secundario): usar `optional(api.xxx(), fallback, 'Nombre legible')`. Para datos primarios (sin los cuales la página no puede funcionar): mostrar un `alert alert-danger` con "Error cargando X. Intente de nuevo." y un botón "Reintentar" que llame a `mount(main)`.

Haz un `grep -rn "\.catch(" src/finance_app/static/js/pages/` para listar todos los casos y clasifícalos antes de editar.

### 2.4 — UI login

Quitar cualquier flujo o link de login visible en la UI de la SPA. Si existe algún link/botón "Login" en la navegación (app.js/sidebar) o en páginas, eliminarlo. La app es local y auth está deshabilitada.

### 2.5 — Auditoría de `sanitize()`

Revisión de cada página en orden de prioridad: `gmail-import.js`, `transactions.js`, `chat.js`, luego el resto.

Para cada página:
- Identificar toda interpolación en `innerHTML` que use datos externos (descripción, payee/lugar, nombres de cuenta/categoría/meta, mensajes de error, campos de email).
- Envolver con `sanitize()` si no lo está.
- Confirmar que `sanitize` está importada de `utils.js`.

Identificar la página que NO importa `sanitize` y corregirla.

No modifiques lógica de negocio, solo las interpolaciones de `innerHTML`.

## Al terminar

Informa al orquestador:
- Cuántos `.catch()` se eliminaron de `client.js` (de 11)
- Cuántos `.catch()` se reemplazaron en páginas (de 23): cuáles → `optional()`, cuáles → error visible
- Confirmación de que dashboard muestra banner y omite cards consolidadas cuando falla la tasa
- Qué página no tenía `sanitize` importado y cómo se corrigió
- Listado de interpolaciones que se envolvieron con `sanitize()` (archivo:línea)
