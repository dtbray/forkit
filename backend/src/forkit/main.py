"""FastAPI application entry point."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .api.ingest import router as ingest_router
from .config import get_settings
from .logging import configure_logging

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.forkit_log_level)

    # S6 — HermitHost coupling guard: refuse to start if exposed without auth
    port_mode = os.environ.get("HERMITHOST_PORT_MODE", "lan")
    auth_mode = os.environ.get("FORKIT_AUTH_MODE", "none")
    if port_mode != "lan" and auth_mode == "none":
        log.critical(
            "forkit refuses to start: HERMITHOST_PORT_MODE is not 'lan' and "
            "FORKIT_AUTH_MODE is 'none'. Set HERMITHOST_PORT_MODE=lan or "
            "set FORKIT_AUTH_MODE=acknowledge_wan_exposed to override."
        )
        raise SystemExit(1)
    if port_mode != "lan" and auth_mode == "acknowledge_wan_exposed":
        import asyncio

        async def _warn_periodically() -> None:
            while True:
                log.critical(
                    "SECURITY WARNING: forkit is running WAN-exposed with no auth. "
                    "Recipe vault is readable/writable by anyone on the internet."
                )
                await asyncio.sleep(60)

        import asyncio

        asyncio.create_task(_warn_periodically())

    log.info(
        "forkit starting",
        db=str(settings.forkit_db_path),
        image_dir=str(settings.forkit_image_dir),
        llm_primary=settings.forkit_llm_primary,
    )
    yield


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="forkit", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.include_router(ingest_router, prefix="/api")


@app.get("/healthz")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "db": str(settings.forkit_db_path),
        "image_dir": str(settings.forkit_image_dir),
    }
