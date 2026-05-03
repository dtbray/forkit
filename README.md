# forkit

Self-hosted family recipe accumulator — paste a URL, get a structured recipe, browse / favorite / cook.

**Status:** Sprint 1 — repo scaffold

## Stack

- **Backend:** Python 3.12 + FastAPI · SQLAlchemy 2.x · Alembic · pytest · ruff · mypy
- **Frontend:** SvelteKit (PWA, SPA mode) · vitest · Playwright
- **Storage:** SQLite + FTS5 (single-file, family scale)
- **LLM:** Ollama (local default) + Anthropic API (fallback) — provider abstraction in backend
- **Deploy:** single-service Docker Compose under [HermitHost](../hermithost) (LAN-only)

## Layout

```
backend/      Python/FastAPI app + parser orchestration
frontend/     SvelteKit PWA
parsers/      Per-site recipe adapters (importable from backend)
ops/
  compose/    HermitHost-aware docker-compose overrides
  migrations/ Alembic migrations
docs/         Repo-local docs (architecture lives in the harness — see below)
```

## Authoritative specs

All architecture, design, decisions, and research live in the harness workspace:

```
/Users/rdemeritt/projects/ai/molt-and-deploy-harness/clients/self/projects/forkit/
```

Key entry points:
- `specs/kickoff-summary.md`
- `specs/decisions-strategic-2026-05-03.md`
- `specs/adr-001-stack-and-pipeline-2026-05-03.md`

## Quickstart

TBD (Sprint 2 — once first feature branch lands).

## License

Not yet decided. Treat as **All Rights Reserved** until set.

## Contributing

See `docs/contributing.md` for branching policy + commit conventions.
