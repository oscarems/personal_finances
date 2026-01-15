# 🔄 Actualizar Base de Datos

Si ves el error: `no such column: categories.initial_amount`

## Solución

Ejecuta este comando para migrar la base de datos:

```bash
python migrate_db.py
```

El script agregará la columna `initial_amount` a la tabla `categories` sin perder tus datos existentes.

## Alternativa: Reiniciar Base de Datos

Si prefieres empezar de cero:

### Opción 1: Eliminar y recrear (Windows)
```powershell
Remove-Item data\finances.db
python init_db.py
```

### Opción 2: Usar el script de reset
```bash
python reset_database.py
# Selecciona opción 2 (Reinicio COMPLETO)
```

---

## Después de migrar

Una vez actualizada la base de datos, puedes:

1. **Iniciar el servidor:**
   ```bash
   python run.py
   ```

2. **Acceder a la aplicación:**
   ```
   http://localhost:8000
   ```

---

## Problemas comunes

### "Base de datos no encontrada"
```bash
python init_db.py
```

### "Columna ya existe"
La migración ya fue aplicada, puedes continuar normalmente.
