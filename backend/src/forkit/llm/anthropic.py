"""Anthropic LLM provider implementation.

Uses Claude Sonnet via tool use for structured JSON output — the most
reliable schema-conformance path on Claude.  The `emit_recipe` tool
schema mirrors the normalizer's expected dict keys.
"""

from __future__ import annotations

import json
import time
from typing import Any

import structlog

from .base import LLMExtractionError

log = structlog.get_logger()

_EMIT_RECIPE_TOOL: dict[str, Any] = {
    "name": "emit_recipe",
    "description": "Emit a structured recipe extracted from the page text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "is_recipe": {
                "type": "boolean",
                "description": "False if the page is not a recipe.",
            },
            "title": {"type": ["string", "null"]},
            "description": {"type": ["string", "null"]},
            "yield_text": {
                "type": ["string", "null"],
                "description": "Original yield string e.g. '4 servings'.",
            },
            "prep_time": {
                "type": ["string", "null"],
                "description": "ISO-8601 duration e.g. 'PT30M'.",
            },
            "cook_time": {"type": ["string", "null"]},
            "total_time": {"type": ["string", "null"]},
            "cuisine": {"type": ["string", "null"]},
            "ingredients": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "raw_text": {"type": "string"},
                        "qty": {"type": ["string", "null"]},
                        "unit": {"type": ["string", "null"]},
                        "item": {"type": ["string", "null"]},
                        "notes": {"type": ["string", "null"]},
                    },
                    "required": ["raw_text"],
                },
            },
            "instructions": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["is_recipe"],
    },
}

_PARSE_INGREDIENTS_TOOL: dict[str, Any] = {
    "name": "emit_ingredients",
    "description": "Emit structured ingredient data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "ingredients": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "raw_text": {"type": "string"},
                        "qty": {"type": ["string", "null"]},
                        "unit": {"type": ["string", "null"]},
                        "item": {"type": ["string", "null"]},
                        "notes": {"type": ["string", "null"]},
                    },
                    "required": ["raw_text"],
                },
            }
        },
        "required": ["ingredients"],
    },
}

_SYSTEM_PROMPT = """\
You extract recipes from web page text.

Rules:
- Use ONLY the emit_recipe tool. Never write prose.
- If a field is unknown, use null. Never invent values.
- Ingredients: preserve original wording in raw_text. Populate qty/unit/item/notes only when unambiguous.
- Instructions: one element per discrete step. Remove ads and "Jump to recipe" boilerplate.
- Times in ISO-8601 format (PT30M, PT1H15M). Yield as the original string.
- If the page is not a recipe, set is_recipe=false.
"""


class AnthropicProvider:
    """LLM provider backed by Anthropic Claude via tool use."""

    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        timeout_sec: int = 30,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_sec

    async def extract_recipe(self, text: str, source_url: str = "") -> dict[str, Any]:
        try:
            import anthropic as anthropic_sdk

            client = anthropic_sdk.AsyncAnthropic(
                api_key=self._api_key,
                timeout=float(self._timeout),
            )

            user_content = (
                f"SOURCE_URL: {source_url}\n\nPAGE_TEXT:\n---\n{text[:6000]}\n---"
            )

            t0 = time.monotonic()
            message = await client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=_SYSTEM_PROMPT,
                tools=[_EMIT_RECIPE_TOOL],  # type: ignore[list-item]
                tool_choice={"type": "auto"},
                messages=[{"role": "user", "content": user_content}],
            )
            latency_ms = int((time.monotonic() - t0) * 1000)

            log.debug(
                "anthropic extract_recipe",
                model=self._model,
                latency_ms=latency_ms,
                stop_reason=message.stop_reason,
            )

            # Find the emit_recipe tool call in the response
            for block in message.content:
                if block.type == "tool_use" and block.name == "emit_recipe":
                    data: dict[str, Any] = block.input  # type: ignore[assignment]
                    if not data.get("is_recipe"):
                        raise LLMExtractionError(
                            f"Anthropic: page is not a recipe for {source_url}"
                        )
                    # Flatten ingredients into raw_text list for normalizer
                    raw_ingredients = [
                        ing.get("raw_text", "")
                        for ing in (data.get("ingredients") or [])
                    ]
                    return {
                        "title": data.get("title"),
                        "description": data.get("description"),
                        "ingredients": raw_ingredients,
                        "instructions": data.get("instructions") or [],
                        "image_url": None,  # Anthropic text path has no image
                        "total_time": data.get("total_time"),
                        "prep_time": data.get("prep_time"),
                        "cook_time": data.get("cook_time"),
                        "yield_text": data.get("yield_text"),
                        "cuisine": data.get("cuisine"),
                    }

            raise LLMExtractionError(
                "Anthropic: no emit_recipe tool call in response"
            )

        except LLMExtractionError:
            raise
        except Exception as exc:
            raise LLMExtractionError(
                f"Anthropic extract_recipe failed: {exc}"
            ) from exc

    async def parse_ingredients(self, raw_lines: list[str]) -> list[dict[str, Any]]:
        try:
            import anthropic as anthropic_sdk

            client = anthropic_sdk.AsyncAnthropic(
                api_key=self._api_key,
                timeout=float(self._timeout),
            )

            user_content = (
                "Parse each ingredient line into structured form.\n\n"
                f"INPUT:\n{json.dumps(raw_lines, ensure_ascii=False)}"
            )

            message = await client.messages.create(
                model=self._model,
                max_tokens=1024,
                tools=[_PARSE_INGREDIENTS_TOOL],  # type: ignore[list-item]
                tool_choice={"type": "auto"},
                messages=[{"role": "user", "content": user_content}],
            )

            for block in message.content:
                if block.type == "tool_use" and block.name == "emit_ingredients":
                    return block.input.get("ingredients", [])  # type: ignore[union-attr]

            raise LLMExtractionError("Anthropic: no emit_ingredients tool call")

        except LLMExtractionError:
            raise
        except Exception as exc:
            raise LLMExtractionError(
                f"Anthropic parse_ingredients failed: {exc}"
            ) from exc

    async def health(self) -> bool:
        try:
            import anthropic as anthropic_sdk

            client = anthropic_sdk.AsyncAnthropic(
                api_key=self._api_key,
                timeout=5.0,
            )
            # Minimal ping — list models or send a tiny message
            await client.messages.create(
                model=self._model,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False
