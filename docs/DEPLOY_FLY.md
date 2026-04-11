# Deploy en Fly.io — Fincas Personales

SQLite persistente en volumen Fly.io. Una sola instancia (free tier).

---

## Pre-requisitos

```bash
# Instalar flyctl (macOS/Linux)
curl -L https://fly.io/install.sh | sh

# Windows (PowerShell)
iwr https://fly.io/install.ps1 -useb | iex

# Autenticarse
fly auth login
```

---

## Primer deploy (solo una vez)

### 1. Crear la aplicación

```bash
# Desde la raíz del proyecto
fly launch \
  --name fincas-personales \
  --region iad \
  --no-deploy
```

> Responde **No** cuando pregunte si quiere hacer deploy ahora.
> Responde **No** si pregunta por PostgreSQL.
> El `fly.toml` ya existe — no lo sobreescribas.

### 2. Crear el volumen persistente (SQLite)

```bash
fly volumes create fincas_data \
  --size 1 \
  --region iad
```

El volumen se monta automáticamente en `/app/data` según el `fly.toml`.
Las bases de datos (`finances.db`, `finances_demo.db`) se crean ahí la primera vez
que arranca la app.

### 3. Configurar secretos

```bash
fly secrets set \
  APP_PASSWORD="tu-password-aqui" \
  SECRET_KEY="genera-una-clave-larga-aleatoria"
```

Para generar `SECRET_KEY`:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

> **Nunca** pongas estos valores en `fly.toml` ni en el repositorio.

### 4. Deploy

```bash
fly deploy
```

La primera vez tarda ~3-5 minutos (build de imagen Docker).
Deploys subsiguientes son más rápidos (~90 seg).

### 5. Verificar

```bash
fly status
fly logs
```

Abre la app:
```bash
fly open
```

---

## Deploys subsiguientes

```bash
# Cada vez que hay cambios
fly deploy
```

---

## Gestión de la base de datos

### Ver logs en tiempo real
```bash
fly logs
```

### Acceder a la consola del contenedor
```bash
fly ssh console
```

### Backup del SQLite desde la consola
```bash
# Dentro de fly ssh console:
sqlite3 /app/data/finances.db ".backup /app/data/finances_backup.db"
```

### Copiar backup a tu máquina local
```bash
# En tu máquina local (no dentro de ssh):
fly sftp get /app/data/finances.db ./finances_backup_$(date +%Y%m%d).db
```

### Restaurar backup
```bash
# Subir archivo local al volumen
fly sftp shell
# Dentro del shell sftp:
put finances.db /app/data/finances.db
```

---

## Escalado

El `fly.toml` configura `min_machines_running = 0` — la app **se duerme** cuando
no hay tráfico (free tier). El primer request después de inactividad tarda ~3-5 seg
en despertar.

Si necesitás que esté siempre activa (tier pago):
```bash
# Cambiar en fly.toml:
# min_machines_running = 1
fly deploy
```

---

## Variables de entorno disponibles

| Variable | Requerida | Descripción |
|---|---|---|
| `APP_PASSWORD` | ✅ Sí | Password de acceso a la app |
| `SECRET_KEY` | ✅ Sí | Clave para firmar cookies |
| `DEMO_MODE` | No | `true` para activar modo demo |
| `DATABASE_URL` | No | Override ruta SQLite principal |
| `DEMO_DATABASE_URL` | No | Override ruta SQLite demo |

---

## Troubleshooting

### La app no arranca
```bash
fly logs
# Buscar errores de APP_PASSWORD o permisos en /app/data
```

### El volumen no tiene espacio
```bash
fly volumes list
# Extender:
fly volumes extend <volume-id> --size 3
```

### Reiniciar la instancia
```bash
fly machine restart
```
