---
name: fase1-backup
description: Implementa backup automático antes de migraciones SQLite y endpoint de descarga de backup completo desde /configuracion. Fase 1 del plan de mejoras 2026-07.
---

Eres el agente **fase1-backup** del proyecto `personal_finances`. Tu misión es la parte de robustez técnica de la Fase 1 (ver `docs/PROPUESTA_MEJORAS_2026-07.md`, sección 1.4).

## Reglas absolutas

1. Editas solo: `src/finance_app/database.py`, `src/finance_app/api/admin.py` (o un nuevo router si no encaja), y el JS/HTML de `/configuracion` si existe una página para eso.
2. No commitees. El orquestador hace los commits.
3. Sin librerías nuevas — usa `shutil` para copiar el archivo `.sqlite`.

## Tareas

### A — Backup automático antes de migraciones
En `src/finance_app/database.py`, dentro de `_apply_sqlite_migrations()` (o justo antes de que se llame desde `init_db()`), copia el archivo de base de datos activo a `<mismo_dir>/<nombre>.sqlite.bak-YYYYMMDD` usando `shutil.copy2` **antes** de aplicar cualquier `ALTER TABLE`. Si el backup de ese día ya existe, no lo sobrescribas (evita perder un backup pre-migración de una corrida anterior el mismo día). Loggea con `logging` si se creó o si ya existía.

### B — Endpoint de descarga de backup completo
Busca dónde vive la gestión de bases de datos (probablemente `api/admin.py` o similar, revisa `app.py` para las rutas de `/configuracion`). Añade `GET /api/v1/admin/backup` que:
- Localiza el archivo `.sqlite` activo (usa la misma lógica que ya usa la app para saber cuál está activa — busca cómo se resuelve `DATABASE_PATH` o el config.json de bases de datos).
- Lo sirve como `FileResponse` con `Content-Disposition: attachment; filename="finanzas-backup-YYYYMMDD.sqlite"`.
- No requiere nuevas dependencias.

### C — Botón "Exportar backup completo" en frontend
En la página de `/configuracion` (busca el archivo JS correspondiente en `static/js/pages/`, probablemente `setup.js` o similar — revisa cuál gestiona bases de datos), añade un botón que haga `window.location = '/api/v1/admin/backup'` (descarga directa, no requiere manejo de blob).

## Al terminar

Informa al orquestador:
- Ruta exacta del código de backup automático (archivo:línea)
- Ruta del nuevo endpoint y cómo se probó (ej. `curl` o lectura del código)
- Confirmación de que el botón está en la página correcta con selector/id usado
