"""LLMProvider Protocol — the interface all provider implementations must satisfy.

Structural typing (PEP 544): no inheritance required.  Any class that
implements the methods below satisfies `isinstance(obj, LLMProvider)` checks
at runtime because the Protocol is `@runtime_checkable`.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Interface for LLM backends used by forkit.

    Methods
    -------
    extract_recipe
        Extract a structured recipe dict from page text.
    parse_ingredients
        Parse a list of raw ingredient strings into structured dicts.
    health
        Lightweight liveness check.  Returns True if the provider is reachable.
    """

    name: str  # "ollama" | "anthropic"

    async def extract_recipe(self, text: str, source_url: str = "") -> dict[str, Any]:
        """Extract recipe fields from page text.

        Args:
            text: Readability-extracted main content of the recipe page.
            source_url: Original URL (included in prompt for context).

        Returns:
            Dict matching the normalizer's expected keys.

        Raises:
            LLMExtractionError: If extraction fails after retries.
        """
        ...

    async def parse_ingredients(
        self, raw_lines: list[str]
    ) -> list[dict[str, Any]]:
        """Parse a batch of raw ingredient strings.

        Args:
            raw_lines: List of raw ingredient text lines.

        Returns:
            List of structured ingredient dicts (one per input line, in order).
        """
        ...

    async def health(self) -> bool:
        """Return True if the provider is reachable and functional."""
        ...


class LLMExtractionError(Exception):
    """Raised when all LLM providers fail to extract a recipe."""
