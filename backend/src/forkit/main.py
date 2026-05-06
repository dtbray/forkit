"""FastAPI application entry point."""

from __future__ import annotations

import os
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .api.ingest import router as ingest_router
from .api.recipes import router as recipes_router
from .api.suggestions import router as suggestions_router
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
app.include_router(recipes_router, prefix="/api")
app.include_router(suggestions_router, prefix="/api")


@app.get("/healthz")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "db": str(settings.forkit_db_path),
        "image_dir": str(settings.forkit_image_dir),
    }


# Serve uploaded recipe images.  The volume mounts at /data/images in Docker;
# create the directory locally so StaticFiles doesn't raise on startup.
_images_dir = pathlib.Path("/data/images")
_images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/data/images", StaticFiles(directory=str(_images_dir)), name="images")

# Serve the SPA after all API routes so API routes take precedence.
# The static/ directory is only present in the Docker image (copied from frontend/build/).
_static_dir = pathlib.Path(__file__).parent / "static"


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str) -> FileResponse:
    # Trailing-slash variants of API routes reach here because the catch-all
    # matches before Starlette's redirect_slashes mechanism fires.
    if full_path.startswith(("api/", "api", "data/")):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    if _static_dir.exists():
        candidate = _static_dir / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        index = _static_dir / "index.html"
        if index.exists():
            return FileResponse(index)
    return JSONResponse({"detail": "Not Found"}, status_code=404)
