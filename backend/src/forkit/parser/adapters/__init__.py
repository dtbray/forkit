"""Per-site adapter registry.

Adapters register themselves via the `@register(hosts=[...])` decorator.
The registry is populated at import time when adapter modules are imported.

Usage::

    from forkit.parser.adapters import get_adapter

    adapter_fn = get_adapter("www.allrecipes.com")
    if adapter_fn:
        result = adapter_fn(html, url)
"""

from __future__ import annotations

from typing import Any, Callable

# hostname_suffix -> callable(html: str, url: str) -> dict | None
_registry: dict[str, Callable[[str, str], dict[str, Any] | None]] = {}


def register(
    hosts: list[str],
) -> Callable[
    [Callable[[str, str], dict[str, Any] | None]],
    Callable[[str, str], dict[str, Any] | None],
]:
    """Decorator: register *fn* for each hostname suffix in *hosts*."""

    def decorator(
        fn: Callable[[str, str], dict[str, Any] | None],
    ) -> Callable[[str, str], dict[str, Any] | None]:
        for host in hosts:
            _registry[host.lower()] = fn
        return fn

    return decorator


def get_adapter(
    hostname: str,
) -> Callable[[str, str], dict[str, Any] | None] | None:
    """Return the adapter callable for *hostname*, or None if none registered.

    Matching is suffix-based: "www.allrecipes.com" matches registration key
    "allrecipes.com".
    """
    normalized = hostname.lower()
    for host, fn in _registry.items():
        if normalized == host or normalized.endswith("." + host):
            return fn
    return None


def _load_builtin_adapters() -> None:
    """Import built-in adapter modules so they self-register."""
    from . import allrecipes_com, seriouseats_com  # noqa: F401


_load_builtin_adapters()
