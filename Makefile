.PHONY: dev build up down start stop restart status logs test migrate shell

# ── Dev ────────────────────────────────────────────────────────────────────────

# Backend dev server (auto-reload, no Docker)
dev:
	cd backend && uvicorn forkit.main:app --reload --host 0.0.0.0 --port 8001

# ── Build ──────────────────────────────────────────────────────────────────────

# Build Docker image (frontend built inside Docker)
build:
	docker compose build

# Rebuild from scratch (no cache)
rebuild:
	docker compose build --no-cache

# ── Lifecycle ──────────────────────────────────────────────────────────────────

# Start stack (build first if image missing)
start: up

up:
	docker compose up -d
	@echo ""
	@$(MAKE) --no-print-directory status

# Stop containers (preserve data volume)
stop: down

down:
	docker compose down

# Stop, rebuild image, start
restart:
	docker compose down
	docker compose build
	docker compose up -d
	@echo ""
	@$(MAKE) --no-print-directory status

# ── Status ─────────────────────────────────────────────────────────────────────

status:
	@echo "=== containers ==="
	@docker compose ps
	@echo ""
	@echo "=== health ==="
	@docker compose ps --format "{{.Name}}  {{.Status}}" | grep -v "^$$" || true
	@echo ""
	@PORT=$$(docker compose port web 8000 2>/dev/null | cut -d: -f2); \
	  if [ -n "$$PORT" ]; then \
	    echo "  app → http://localhost:$$PORT"; \
	    curl -sf http://localhost:$$PORT/healthz | python3 -m json.tool 2>/dev/null || echo "  (healthz not ready yet)"; \
	  else \
	    echo "  (not running)"; \
	  fi

# ── Data ───────────────────────────────────────────────────────────────────────

# Run Alembic migrations inside the running container
migrate:
	docker compose exec web alembic upgrade head

# Open a shell in the web container
shell:
	docker compose exec web /bin/bash

# Tail logs (all services, or: make logs s=web)
logs:
	docker compose logs -f $(s)

# ── Test ───────────────────────────────────────────────────────────────────────

test:
	cd backend && python -m pytest
	cd frontend && npm test
