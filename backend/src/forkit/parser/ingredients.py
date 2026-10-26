"""Ingredient structurer — hybrid deterministic + LLM retry pipeline.

Stage 1: ingredient-parser-nlp (deterministic, ~85% accuracy, sub-millisecond).
Stage 2: LLM retry on low-confidence rows (handled by caller; interface locked here).

`structure_ingredient(raw_text)` returns a dict with:
    raw_text, qty, unit, item, notes, canonical_token
"""

from __future__ import annotations

from typing import Any


def structure_ingredient(raw_text: str) -> dict[str, Any]:
    """Parse a raw ingredient string into structured form.

    Uses ingredient-parser-nlp as the deterministic first stage.
    Falls back to a raw-text-only dict on any parse error.

    Args:
        raw_text: e.g. "2 1/2 cups all-purpose flour, sifted"

    Returns:
        Dict with keys: raw_text, qty, unit, item, notes, canonical_token.
    """
    try:
        from ingredient_parser import parse_ingredient  # type: ignore[import-untyped]

        result = parse_ingredient(raw_text)

        qty: str | None = None
        unit: str | None = None

        if result.amount:
            first_amount = result.amount[0]
            qty_val = getattr(first_amount, "quantity", None)
            qty = str(qty_val).strip() if qty_val is not None else None
            unit_val = getattr(first_amount, "unit", None)
            unit = str(unit_val).strip() if unit_val else None

        def text_parts(value: Any) -> str | None:
            # Current ingredient-parser returns a list of name spans. Older
            # versions and optional fields may return a single IngredientText.
            parts = value if isinstance(value, list) else [value]
            texts = [str(part.text).strip() for part in parts if getattr(part, "text", None)]
            return ", ".join(texts) or None

        item_text = text_parts(result.name)
        notes_text = text_parts(result.comment)

        canonical_token = (item_text or raw_text).lower().strip()

        return {
            "raw_text": raw_text,
            "qty": qty,
            "unit": unit,
            "item": item_text or raw_text,
            "notes": notes_text if notes_text else None,
            "canonical_token": canonical_token,
        }
    except Exception:
        # Fail open: preserve raw text so the recipe is still usable
        return {
            "raw_text": raw_text,
            "qty": None,
            "unit": None,
            "item": raw_text,
            "notes": None,
            "canonical_token": raw_text.lower().strip(),
        }
