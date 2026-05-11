"""POST /api/ingest — recipe ingestion endpoint (S7: rate-limited 10/min).

This module is now a thin HTTP wrapper. All business logic lives in
forkit.services.ingest.ingest_url() so that Phase 2 /promote can call it
directly without an HTTP self-call (ADR-002 Section 5.2).
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, field_validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from ..db import get_session
from ..services.ingest import ingest_url

log = structlog.get_logger()

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


class IngestRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def url_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("url must not be empty")
        return v


class IngestResponse(BaseModel):
    recipe_id: str
    parser_source: str
    parser_confidence: float


@router.post("/ingest", response_model=IngestResponse)
@limiter.limit("10/minute")
async def ingest_recipe(
    request: Request,
    body: IngestRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Fetch a recipe URL, parse it, persist to DB, return the recipe ID.

    Rate limited to 10 requests/minute per IP (S7).
    SSRF-safe fetcher enforces scheme allowlist + IP blocklist (S1).
    HTML sanitized on store via bleach (S2).
    """
    return await ingest_url(body.url, session)
