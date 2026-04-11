FROM python:3.11-slim

# ── Sistema ───────────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Directorio de trabajo ─────────────────────────────────────────────────────
WORKDIR /app

# ── Dependencias Python (capa cacheada) ───────────────────────────────────────
COPY requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt

# ── Código fuente ─────────────────────────────────────────────────────────────
COPY src/ ./src/

# ── Directorio de datos (mount point del volumen persistente) ─────────────────
# El volumen de Fly.io se monta en /app/data en runtime.
# BASE_DIR en settings.py resuelve a /app → BASE_DIR/data = /app/data ✓
RUN mkdir -p /app/data/uploads

# ── Puerto ────────────────────────────────────────────────────────────────────
EXPOSE 8000

# ── Arranque producción (sin --reload) ────────────────────────────────────────
CMD ["uvicorn", "finance_app.app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--app-dir", "src", \
     "--workers", "1", \
     "--log-level", "info"]
