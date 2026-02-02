# Sincronización de gastos desde Telegram (Plan A)

Este módulo permite registrar transacciones enviando mensajes a un bot de Telegram usando **polling** (sin webhooks) y guardando los datos en la base de datos local.

## Requisitos

1. Crear un bot con [@BotFather](https://t.me/BotFather) y obtener el token.
2. Obtener tu `chat_id`:
   - Envía un mensaje al bot.
   - Abre en el navegador: `https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates`
   - Busca el campo `chat.id`.
3. Configurar variables de entorno:

```bash
export TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
export TELEGRAM_ALLOWED_CHAT_ID="123456789"
export TELEGRAM_DEFAULT_CURRENCY="COP"
export TELEGRAM_DEFAULT_ACCOUNT="Bancolombia"
```

## Migración opcional (requerida una sola vez)

Se agregan las columnas `source` y `source_id` a `transactions` para garantizar idempotencia.

```bash
python -m finance_app.scripts.migrate_telegram_source_fields
```

> Nota: esta migración es necesaria antes del primer sync. No se guardan secretos en la base de datos.

## Ejecutar sincronización

```bash
python -m finance_app.sync.telegram
```

El comando:
- Lee mensajes con `getUpdates` usando `offset`.
- Filtra por `TELEGRAM_ALLOWED_CHAT_ID`.
- Inserta transacciones con `source="telegram"` y `source_id=<update_id>`.
- Guarda el último `update_id` en la tabla `telegram_settings`.

## Formato de mensajes soportado

Ejemplos:

```
-28500 cop uber transporte
-12.50 usd starbucks cafe
-45000 cop mercado
2026-02-01 -18000 cop cine
-28500 cop @davivienda uber transporte
```

Reglas de parseo:
- Si no hay signo, se asume gasto (negativo).
- Si no hay moneda, se usa `TELEGRAM_DEFAULT_CURRENCY` o la moneda base.
- `@<account>` usa una cuenta específica (si no existe, se usa la cuenta por defecto y se loggea warning).
- `payee` = primer token de texto.
- `category` = último token si coincide con alguna categoría existente.
- Si no hay categoría, el resto del texto va a `memo`.

## Logs esperados

El script reporta:
- total de updates leídos
- cuántos insertó
- cuántos ignoró
