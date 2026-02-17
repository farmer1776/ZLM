# syntax=docker/dockerfile:1
# ---- Builder stage ----
FROM python:3.9-slim AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc default-libmysqlclient-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Runtime stage ----
FROM python:3.9-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends default-libmysqlclient-dev && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r zlm && useradd -r -g zlm -d /app -s /sbin/nologin zlm

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY apps/ ./apps/
COPY cli/ ./cli/
COPY conf/app.conf.example ./conf/app.conf.example
COPY config.py database.py dependencies.py main.py template_filters.py ./
COPY core/ ./core/
COPY deploy/gunicorn.conf.py ./deploy/gunicorn.conf.py
COPY deploy/entrypoint.sh ./deploy/entrypoint.sh
COPY middleware/ ./middleware/
COPY models/ ./models/
COPY routers/ ./routers/
COPY services/ ./services/
COPY static/ ./static/
COPY templates/ ./templates/

# Create data directories and set ownership
RUN mkdir -p /app/data/uploads /app/data/exports /app/data/logs /app/conf && \
    chown -R zlm:zlm /app

USER zlm

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
