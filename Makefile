.PHONY: dev build up down start stop restart status logs test migrate shell

DC := docker compose -f docker-compose.yml -f docker-compose.local.yml

# ── Dev ────────────────────────────────────────────────────────────────────────

# Backend dev server (auto-reload, no Docker)
dev:
	cd backend && uvicorn forkit.main:app --reload --host 0.0.0.0 --port 8001

# ── Build ──────────────────────────────────────────────────────────────────────

# Build Docker image (frontend built inside Docker)
build:
	$(DC) build

# Rebuild from scratch (no cache)
rebuild:
	$(DC) build --no-cache

# ── Lifecycle ──────────────────────────────────────────────────────────────────

# Start stack (build first if image missing)
start: up

up:
	$(DC) up -d
	@echo ""
	@$(MAKE) --no-print-directory status

# Stop containers (preserve data volume)
stop: down

down:
	$(DC) down

# Stop, rebuild image, start
restart:
	$(DC) down
	$(DC) build
	$(DC) up -d
	@echo ""
	@$(MAKE) --no-print-directory status

# ── Status ─────────────────────────────────────────────────────────────────────

status:
	@echo "=== containers ==="
	@$(DC) ps
	@echo ""
	@echo "=== health ==="
	@$(DC) ps --format "{{.Name}}  {{.Status}}" | grep -v "^$$" || true
	@echo ""
	@PORT=$$($(DC) port web 8000 2>/dev/null | cut -d: -f2); \
	  if [ -n "$$PORT" ]; then \
	    echo "  app → http://localhost:$$PORT"; \
	    curl -sf http://localhost:$$PORT/healthz | python3 -m json.tool 2>/dev/null || echo "  (healthz not ready yet)"; \
	  else \
	    echo "  (not running)"; \
	  fi

# ── Data ───────────────────────────────────────────────────────────────────────

# Run Alembic migrations inside the running container
migrate:
	$(DC) exec web alembic upgrade head

# Open a shell in the web container
shell:
	$(DC) exec web /bin/bash

# Tail logs (all services, or: make logs s=web)
logs:
	$(DC) logs -f $(s)

# ── Test ───────────────────────────────────────────────────────────────────────

test:
	cd backend && python -m pytest
	cd frontend && npm test
