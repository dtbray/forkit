# syntax=docker/dockerfile:1

# ── Stage 1: build frontend ─────────────────────────────────────────────────────
FROM node:22-slim AS frontend-builder

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ── Stage 2: build Python dependencies ─────────────────────────────────────────
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

RUN pip install --no-cache-dir --prefix=/install .


# ── Stage 3: runtime image ─────────────────────────────────────────────────────
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

# Bundle the POS tagger: the unprivileged runtime must not download language data.
ENV NLTK_DATA=/usr/local/share/nltk_data
RUN python -m nltk.downloader -d /usr/local/share/nltk_data averaged_perceptron_tagger_eng \
    && python -c "import nltk; nltk.data.find('taggers/averaged_perceptron_tagger_eng')"

# Copy application source
COPY backend/src ./src
COPY backend/pyproject.toml ./

# Copy Alembic config + migrations so the container can self-migrate on startup
COPY alembic.ini ./
COPY ops/ ./ops/

# Copy frontend static build so FastAPI StaticFiles can serve the SPA
COPY --from=frontend-builder /app/build ./src/forkit/static

# Ensure the data volume mount-point is owned by forkit before privilege drop
RUN mkdir -p /data && chown forkit:forkit /data

ENV PYTHONPATH=/app/src

USER forkit

EXPOSE 8000

# Run migrations then start the server
CMD ["sh", "-c", "alembic upgrade head && uvicorn forkit.main:app --host 0.0.0.0 --port 8000"]
