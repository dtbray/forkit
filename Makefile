.PHONY: dev build up down test migrate logs

# Run the backend in development mode with auto-reload
dev:
	cd backend && uvicorn forkit.main:app --reload --host 0.0.0.0 --port 8000

# Build the frontend then build the Docker image
build:
	cd frontend && npm run build
	docker compose build

# Start all services in detached mode
up:
	docker compose up -d

# Stop and remove containers
down:
	docker compose down

# Run backend and frontend test suites
test:
	cd backend && python -m pytest
	cd frontend && npm test

# Run database migrations
migrate:
	cd backend && alembic upgrade head

# Tail all service logs
logs:
	docker compose logs -f
