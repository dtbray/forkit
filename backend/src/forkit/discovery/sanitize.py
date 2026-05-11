"""Shared sanitize helper — strips all HTML from user-controlled text.

Security condition S5: applied to all title/summary fields before storage
or return to callers.
"""

from __future__ import annotations

import bleach


def sanitize(text: str | None) -> str | None:
    """Strip all HTML tags — security condition S5."""
    if not text:
        return None
    cleaned = bleach.clean(text, tags=[], attributes={}, strip=True).strip()
    return cleaned or None
