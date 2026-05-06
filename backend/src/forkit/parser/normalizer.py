"""Recipe field normalizer (S2 — bleach HTML sanitization).

`normalize(raw)` is the single entry point.  It:
* Sanitizes HTML in text fields via bleach allowlist (S2).
* Converts ISO-8601 duration strings and "N minutes" prose to PT…M form.
* Strips leading/trailing whitespace from all string fields.
"""

from __future__ import annotations

import re
from typing import Any

import bleach

# Allowed HTML tags for rich-text fields (description, instruction steps).
_ALLOWED_TAGS = ["p", "br", "strong", "em", "ul", "ol", "li", "a"]
_ALLOWED_ATTRS: dict[str, list[str]] = {"a": ["href"]}

# Matches "30 minutes", "1 hour 15 minutes", "1 hr", "45 min", etc.
_TIME_PROSE_RE = re.compile(
    r"(?:(\d+)\s*(?:hours?|hrs?))?[\s,]*(?:(\d+)\s*(?:minutes?|mins?))?",
    re.IGNORECASE,
)

# Already an ISO-8601 duration
_ISO_DURATION_RE = re.compile(r"^PT\d+[HMS]", re.IGNORECASE)


def _sanitize(text: str) -> str:
    """Strip disallowed HTML tags and attributes; preserve allowlisted markup."""
    cleaned = bleach.clean(
        text,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        strip=True,
    )
    return cleaned.strip()


def _to_iso_duration(value: str | None) -> str | None:
    """Convert a time value to ISO-8601 duration string or None.

    Accepts:
    * Already-ISO strings like "PT30M" — returned as-is (uppercased).
    * Prose like "30 minutes", "1 hour 15 minutes".
    * Plain integers interpreted as minutes.

    Returns None if the value cannot be parsed.
    """
    if not value:
        return None
    value = value.strip()

    # Already ISO 8601
    if _ISO_DURATION_RE.match(value):
        return value.upper()

    # Try plain integer (minutes)
    try:
        mins = int(value)
        return f"PT{mins}M"
    except ValueError:
        pass

    # Prose matching
    match = _TIME_PROSE_RE.fullmatch(value.strip())
    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        total_min = hours * 60 + minutes
        if total_min:
            return f"PT{total_min}M"

    return None


def _clean_str(value: Any) -> Any:
    """Strip whitespace from string values; pass through non-strings unchanged."""
    if isinstance(value, str):
        return value.strip()
    return value


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw parser output dict into a clean recipe dict.

    Args:
        raw: Dict from JSON-LD extractor, adapter, or LLM.  Expected keys:
            title, description, ingredients (list[str]), instructions (list[str]),
            image_url, total_time, prep_time, cook_time, yield_text, cuisine.

    Returns:
        Normalized dict with the same keys.
    """
    title = _sanitize(str(raw.get("title") or "")).strip()
    description_raw = raw.get("description")
    description = _sanitize(str(description_raw)).strip() if description_raw else None

    # Ingredients — plain text, no HTML allowed
    ingredients: list[str] = []
    for ing in raw.get("ingredients") or []:
        cleaned = bleach.clean(str(ing), tags=[], strip=True).strip()
        if cleaned:
            ingredients.append(cleaned)

    # Instructions — allow limited markup for formatting
    instructions: list[str] = []
    for step in raw.get("instructions") or []:
        cleaned = _sanitize(str(step))
        if cleaned:
            instructions.append(cleaned)

    return {
        "title": title,
        "description": description,
        "ingredients": ingredients,
        "instructions": instructions,
        "image_url": _clean_str(raw.get("image_url")),
        "total_time": _to_iso_duration(raw.get("total_time")),
        "prep_time": _to_iso_duration(raw.get("prep_time")),
        "cook_time": _to_iso_duration(raw.get("cook_time")),
        "yield_text": _clean_str(raw.get("yield_text")),
        "cuisine": _clean_str(raw.get("cuisine")),
    }
