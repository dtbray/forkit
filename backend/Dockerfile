# syntax=docker/dockerfile:1
# Multi-stage build — security gate S8: non-root user (forkit, UID 1000)

# ── Stage 1: build dependencies ────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tooling
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libxml2-dev \
        libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/README.md ./
# Copy source so hatchling can resolve the package metadata
COPY backend/src ./src

RUN pip install --no-cache-dir --prefix=/install -e .


# ── Stage 2: runtime image ─────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# S8 — non-root user
RUN groupadd --gid 1000 forkit && \
    useradd --uid 1000 --gid 1000 --no-create-home --shell /bin/false forkit

WORKDIR /app

# Runtime system dependencies (libxml2/libxslt needed by readability-lxml)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libxml2 \
        libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY backend/src ./src
COPY backend/pyproject.toml ./

# Copy frontend static build so FastAPI StaticFiles can serve the SPA
COPY frontend/build ./src/forkit/static

# Ensure the data volume mount-point is owned by forkit before privilege drop
RUN mkdir -p /data && chown forkit:forkit /data

USER forkit

EXPOSE 8000

CMD ["uvicorn", "forkit.main:app", "--host", "0.0.0.0", "--port", "8000"]
