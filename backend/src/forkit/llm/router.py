"""Routed LLM provider: primary → fallback, with llm_calls telemetry logging.

Every call — success or failure — writes a row to the `llm_calls` SQLite
table (created by migration 0002).

Fallback is attempted once on:
* Any exception from the primary (transport, timeout, LLMExtractionError).
* If both fail, LLMExtractionError is raised to the caller.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

from .base import LLMExtractionError, LLMProvider

log = structlog.get_logger()


def _write_llm_call(
    session: Session,
    *,
    provider: str,
    method: str,
    success: bool,
    latency_ms: int,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    error: str | None = None,
) -> None:
    """Insert a telemetry row into llm_calls via raw SQL (table may exist before ORM)."""
    from sqlalchemy import text

    session.execute(
        text(
            """
            INSERT INTO llm_calls
              (created_at, provider, method, success, latency_ms, input_tokens, output_tokens, error)
            VALUES
              (:created_at, :provider, :method, :success, :latency_ms, :input_tokens, :output_tokens, :error)
            """
        ),
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "method": method,
            "success": 1 if success else 0,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "error": error,
        },
    )
    session.commit()


class RoutedLLMProvider:
    """Wraps a primary and optional fallback LLMProvider with telemetry logging.

    Args:
        primary: The primary provider to try first.
        fallback: Optional fallback provider.  None = no fallback.
        session: SQLAlchemy Session for llm_calls logging.
    """

    name = "routed"

    def __init__(
        self,
        primary: LLMProvider,
        fallback: LLMProvider | None,
        session: Session,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._session = session

    async def extract_recipe(self, text: str, source_url: str = "") -> dict[str, Any]:
        return await self._call(
            method="extract_recipe",
            primary_call=lambda: self._primary.extract_recipe(text, source_url),
            fallback_call=(
                lambda: self._fallback.extract_recipe(text, source_url)
                if self._fallback
                else None
            ),
        )

    async def parse_ingredients(
        self, raw_lines: list[str]
    ) -> list[dict[str, Any]]:
        return await self._call(  # type: ignore[return-value]
            method="parse_ingredients",
            primary_call=lambda: self._primary.parse_ingredients(raw_lines),
            fallback_call=(
                lambda: self._fallback.parse_ingredients(raw_lines)
                if self._fallback
                else None
            ),
        )

    async def health(self) -> bool:
        return await self._primary.health()

    async def _call(
        self,
        *,
        method: str,
        primary_call: Any,
        fallback_call: Any,
    ) -> Any:
        # Try primary
        t0 = time.monotonic()
        try:
            result = await primary_call()
            latency_ms = int((time.monotonic() - t0) * 1000)
            self._log_call(
                provider=self._primary.name,
                method=method,
                success=True,
                latency_ms=latency_ms,
            )
            return result
        except Exception as primary_exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            log.warning(
                "llm primary failed",
                provider=self._primary.name,
                method=method,
                error=str(primary_exc),
            )
            self._log_call(
                provider=self._primary.name,
                method=method,
                success=False,
                latency_ms=latency_ms,
                error=str(primary_exc),
            )

        # Try fallback
        if self._fallback is None or fallback_call is None:
            raise LLMExtractionError(
                f"Primary provider '{self._primary.name}' failed and no fallback configured."
            )

        t1 = time.monotonic()
        try:
            result = await fallback_call()
            latency_ms = int((time.monotonic() - t1) * 1000)
            self._log_call(
                provider=self._fallback.name,
                method=method,
                success=True,
                latency_ms=latency_ms,
            )
            return result
        except Exception as fallback_exc:
            latency_ms = int((time.monotonic() - t1) * 1000)
            log.error(
                "llm fallback also failed",
                provider=self._fallback.name,
                method=method,
                error=str(fallback_exc),
            )
            self._log_call(
                provider=self._fallback.name,
                method=method,
                success=False,
                latency_ms=latency_ms,
                error=str(fallback_exc),
            )
            raise LLMExtractionError(
                f"Both primary ('{self._primary.name}') and fallback ('{self._fallback.name}') "
                f"failed for method '{method}'."
            ) from fallback_exc

    def _log_call(
        self,
        *,
        provider: str,
        method: str,
        success: bool,
        latency_ms: int,
        error: str | None = None,
    ) -> None:
        try:
            _write_llm_call(
                self._session,
                provider=provider,
                method=method,
                success=success,
                latency_ms=latency_ms,
                error=error,
            )
        except Exception as exc:
            # Telemetry must not crash the request
            log.warning("llm_calls telemetry write failed", error=str(exc))
