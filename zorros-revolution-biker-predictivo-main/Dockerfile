# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Etapa 1: construcción del entorno virtual.
# Se separa del runtime para que la imagen final no arrastre pip ni las cachés
# de compilación (scikit-learn, pandas y numpy pesan bastante).
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

COPY backend/requirements.txt .

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt


# ---------------------------------------------------------------------------
# Etapa 2: runtime.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# curl es necesario para el HEALTHCHECK.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Usuario sin privilegios: nunca correr la app como root.
RUN groupadd --system zorros \
    && useradd --system --gid zorros --create-home --home-dir /home/zorros zorros

COPY --from=builder /opt/venv /opt/venv

# app.main resuelve el frontend como `parents[2] / "frontend"`; con el código en
# /app/app/main.py eso apunta a /frontend, de ahí esta disposición.
WORKDIR /app
COPY backend/ /app/
COPY frontend/ /frontend/

# Punto de montaje del volumen de artefactos del modelo (ver ARTIFACTS_DIR).
RUN mkdir -p /var/lib/zorros/artifacts \
    && chown -R zorros:zorros /var/lib/zorros /app /frontend

USER zorros

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# El esquema se crea en un paso previo y en un solo proceso: si se deja que lo
# hagan los workers al importar la app, sobre PostgreSQL compiten creando los
# tipos ENUM y uno muere con "duplicate key ... pg_type_typname_nsp_index".
CMD ["sh", "-c", "python -m app.init_db && exec gunicorn app.main:app -c gunicorn_conf.py"]
