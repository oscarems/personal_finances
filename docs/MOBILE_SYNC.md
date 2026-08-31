# Consulta móvil — sync por WiFi (local)

Vista read-only para revisar finanzas desde el celular cuando el PC tiene la app encendida. Si el PC está apagado, muestra la **última copia en caché** del navegador (puede estar desactualizada).

---

## Cómo usarlo

1. En el PC: `python run.py` (app en `http://0.0.0.0:8000`).
2. PC y celular en la **misma WiFi**.
3. En el celular: `http://<IP-del-PC>:8000/mobile`  
   Ejemplo: `http://192.168.1.45:8000/mobile`
4. Pulsa **↻** para sincronizar de nuevo.

**Tip:** guarda la URL en favoritos del navegador del celular.

---

## Qué muestra

| Dato | Fuente |
|------|--------|
| Listo para asignar | Presupuesto mes actual |
| Disponible en gastos / ahorros | Totales del presupuesto |
| Atención (categorías en ámbar/rojo) | Misma lógica que dashboard |
| Saldos por moneda | Cuentas abiertas |

No permite crear transacciones (solo lectura).

---

## Arquitectura

```
┌─────────────┐     WiFi LAN      ┌──────────────────────┐
│   Celular   │ ─── GET /api/mobile/snapshot ──▶│  PC (FastAPI) │
│  /mobile    │ ◀── JSON compacto ─────────────│  SQLite       │
└─────────────┘                                 └──────────────────────┘
       │
       ▼
 localStorage (`pf_mobile_snapshot`)
```

### Endpoint

`GET /api/mobile/snapshot`

Respuesta ejemplo:

```json
{
  "generated_at": "2026-08-30T17:30:00+00:00",
  "month": "2026-08",
  "currency": "COP",
  "ready_to_assign": 450000,
  "totals": { "available": 1200000, "savings": 800000, "in_accounts": 2450000 },
  "accounts_by_currency": { "COP": 2000000, "USD": 120 },
  "attention": [
    { "name": "Comida", "pct_used": 92, "status": "warn", "available": 50000 }
  ]
}
```

### Caché en el cliente

- Tras sync exitosa → guarda en `localStorage`.
- Si falla la red → muestra caché + banner **“Datos en caché”**.
- No hay sync en background ni push: el usuario refresca manualmente.

---

## Limitaciones (por diseño)

| Limitación | Motivo |
|------------|--------|
| Datos pueden estar viejos | PC apagado o sin sync reciente |
| Solo misma red local | App no expuesta a internet |
| Sin editar | Evitar conflictos offline |
| Sin notificaciones push | Sin servidor en la nube |

---

## Evolución futura (opcional)

1. **PWA** — “Añadir a pantalla de inicio” + icono.
2. **Sync automática** al abrir `/mobile` si hay red.
3. **QR en Setup** — escaneas IP:puerto desde el PC.
4. **Tailscale** — consulta fuera de casa sin abrir puertos.
5. **App nativa** — solo si hace falta widget o notificaciones OS.

Por ahora la opción 1–2 cubren el caso “mirar cuánto me queda desde el celular” sin complejidad extra.
