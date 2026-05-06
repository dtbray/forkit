"""Structured logging configuration with API key redaction (S5)."""

from __future__ import annotations

import logging
import re
from typing import Any

import structlog


# Patterns that must never appear in log output
_REDACT_KEYS = frozenset({"authorization", "x-api-key", "forkit_anthropic_api_key"})
_API_KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9\-_]{10,}")


def _redact_processor(
    logger: Any, method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Strip Authorization headers and Anthropic API key values from event dicts."""
    for key in list(event_dict.keys()):
        if key.lower() in _REDACT_KEYS:
            event_dict[key] = "[REDACTED]"
            continue
        val = event_dict[key]
        if isinstance(val, str) and _API_KEY_RE.search(val):
            event_dict[key] = _API_KEY_RE.sub("[REDACTED]", val)
        elif isinstance(val, dict):
            # Recurse one level — covers headers dicts
            for inner_key in list(val.keys()):
                if inner_key.lower() in _REDACT_KEYS:
                    val[inner_key] = "[REDACTED]"
                elif isinstance(val[inner_key], str) and _API_KEY_RE.search(
                    val[inner_key]
                ):
                    val[inner_key] = _API_KEY_RE.sub("[REDACTED]", val[inner_key])
    return event_dict


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog with JSON renderer and API key redaction."""
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _redact_processor,
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
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *shared_processors,
            structlog.processors.JSONRenderer(),
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
