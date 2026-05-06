"""Ollama LLM provider implementation.

Uses httpx to POST to the Ollama `/api/generate` endpoint with
`format="json"` (JSON mode — syntactically valid JSON guaranteed).

Post-generation: response JSON is validated via Pydantic.  If validation
fails, a single retry with a corrective instruction is attempted before
raising LLMExtractionError.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import structlog

from .base import LLMExtractionError

log = structlog.get_logger()

_SYSTEM_PROMPT = """\
You extract recipes from web page text into a strict JSON schema.

Rules:
- Output ONLY valid JSON matching the schema below. No markdown, no explanations.
- If a field is unknown, use null. Never invent values. Never guess yields or times.
- Ingredients: preserve original wording in "raw_text". Populate qty, unit, item, notes only when unambiguous; leave null otherwise.
- Instructions: one element per discrete step. Do not collapse. Do not paraphrase beyond removing inline ads or "Jump to recipe" boilerplate.
- Times in ISO-8601 duration format (e.g. "PT30M", "PT1H15M"). Yield as the original string ("4 servings", "1 loaf").
- If the page is not a recipe, set "is_recipe": false and leave other fields null.

Schema:
{
  "is_recipe": true,
  "title": "string",
  "description": "string|null",
  "yield_text": "string|null",
  "prep_time": "PT…|null",
  "cook_time": "PT…|null",
  "total_time": "PT…|null",
  "cuisine": "string|null",
  "ingredients": [
    {"raw_text": "string", "qty": "string|null", "unit": "string|null", "item": "string|null", "notes": "string|null"}
  ],
  "instructions": ["string"]
}
"""

_INGREDIENT_PROMPT = """\
Parse each ingredient line into {qty, unit, item, notes}. Use null for missing fields.
Units: normalize to lowercase singular (cup, tbsp, tsp, oz, lb, g, kg, ml, l, clove, pinch, piece).
Item: the canonical food noun, lowercase, no adjectives (adjectives go in notes).
Notes: preparation, packaging, optional flag.

INPUT:
{lines_json}

OUTPUT:
JSON array, one object per input line, in order. Each object must have keys: raw_text, qty, unit, item, notes.
"""


class OllamaProvider:
    """LLM provider backed by a local Ollama instance."""

    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout_sec: int = 30) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_sec

    async def extract_recipe(self, text: str, source_url: str = "") -> dict[str, Any]:
        prompt = f"SOURCE_URL: {source_url}\n\nPAGE_TEXT:\n---\n{text[:6000]}\n---"
        result = await self._generate(prompt, attempt=1)

        if not result.get("is_recipe"):
            raise LLMExtractionError(
                f"Ollama: page is not a recipe (is_recipe=false) for {source_url}"
            )
        return result

    async def parse_ingredients(self, raw_lines: list[str]) -> list[dict[str, Any]]:
        lines_json = json.dumps(raw_lines, ensure_ascii=False)
        prompt = _INGREDIENT_PROMPT.format(lines_json=lines_json)
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "system": "You parse ingredient lists into structured JSON.",
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0.1, "num_ctx": 4096},
                },
            )
        latency_ms = int((time.monotonic() - t0) * 1000)
        response.raise_for_status()
        raw_json = response.json().get("response", "")
        try:
            parsed = json.loads(raw_json)
            if not isinstance(parsed, list):
                parsed = parsed.get("ingredients", [])
            return parsed
        except json.JSONDecodeError as exc:
            raise LLMExtractionError(
                f"Ollama parse_ingredients: invalid JSON response: {exc}"
            ) from exc

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def _generate(self, prompt: str, attempt: int) -> dict[str, Any]:
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=float(self._timeout)) as client:
            response = await client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "system": _SYSTEM_PROMPT,
                    "prompt": prompt,
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0.1, "num_ctx": 8192},
                },
            )
        latency_ms = int((time.monotonic() - t0) * 1000)

        response.raise_for_status()
        raw_json = response.json().get("response", "")

        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            if attempt == 1:
                log.warning("ollama: JSON parse failure, retrying", error=str(exc))
                retry_prompt = (
                    prompt
                    + "\n\nYour previous response was not valid JSON. "
                    "Output ONLY the JSON object matching the schema."
                )
                return await self._generate(retry_prompt, attempt=2)
            raise LLMExtractionError(
                f"Ollama: invalid JSON after retry: {exc}"
            ) from exc

        return parsed
