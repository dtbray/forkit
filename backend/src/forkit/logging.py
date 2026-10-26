"""Structured logging configuration with API key redaction (S5)."""

from __future__ import annotations

import logging
import re
from typing import Any

import structlog

# Patterns that must never appear in log output
_REDACT_KEYS = frozenset({"authorization", "x-api-key", "forkit_anthropic_api_key"})
_API_KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9\-_]{10,}")


def _redact_processor(logger: Any, method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Strip Authorization headers and Anthropic API key values from event dicts."""

    def redact(value: Any) -> Any:
        if isinstance(value, str):
            return _API_KEY_RE.sub("[REDACTED]", value)
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if str(key).lower() in _REDACT_KEYS else redact(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [redact(item) for item in value]
        return value

    return redact(event_dict)


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog with JSON renderer and API key redaction."""
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        # Foreign (stdlib) records still have _record metadata here, allowing
        # add_logger_name to work even when ProcessorFormatter passes logger=None.
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            # Redact after exception rendering, covering messages and traceback text.
            _redact_processor,
            structlog.processors.JSONRenderer(),
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
