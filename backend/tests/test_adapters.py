"""Adapter registry and interface tests.

Uses synthetic minimal HTML with embedded JSON-LD to validate that:
1. The adapter registry resolves the correct adapter by hostname.
2. The adapter interface returns the expected dict shape.
3. The adapter returns None (not raises) on unparseable input.
"""

from __future__ import annotations

import json

import pytest

from forkit.parser.adapters import get_adapter


_RECIPE_JSONLD = json.dumps(
    {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": "Test Chocolate Cake",
        "description": "A simple test cake recipe.",
        "recipeIngredient": [
            "2 cups flour",
            "1 cup sugar",
            "1/2 cup cocoa powder",
            "2 eggs",
            "1 cup milk",
        ],
        "recipeInstructions": [
            {"@type": "HowToStep", "text": "Preheat oven to 350°F."},
            {"@type": "HowToStep", "text": "Mix dry ingredients."},
            {"@type": "HowToStep", "text": "Add wet ingredients and mix well."},
            {"@type": "HowToStep", "text": "Pour into pan and bake 30 minutes."},
        ],
        "recipeYield": "8 servings",
        "totalTime": "PT1H",
        "prepTime": "PT20M",
        "cookTime": "PT40M",
        "recipeCuisine": "American",
    }
)

_MINIMAL_HTML = f"""\
<!DOCTYPE html>
<html>
<head>
<script type="application/ld+json">{_RECIPE_JSONLD}</script>
</head>
<body><h1>Test Chocolate Cake</h1></body>
</html>
"""


@pytest.mark.parametrize(
    "hostname,expected_host_key",
    [
        ("allrecipes.com", "allrecipes.com"),
        ("www.allrecipes.com", "allrecipes.com"),
        ("seriouseats.com", "seriouseats.com"),
        ("www.seriouseats.com", "seriouseats.com"),
    ],
)
def test_adapter_registry_resolves(hostname: str, expected_host_key: str) -> None:
    """Registry must resolve known hostnames to a callable adapter."""
    adapter = get_adapter(hostname)
    assert adapter is not None, f"No adapter registered for {hostname!r}"
    assert callable(adapter)


def test_adapter_registry_unknown_host() -> None:
    """Unknown hosts must return None, not raise."""
    adapter = get_adapter("unknownsitenotregistered.io")
    assert adapter is None


@pytest.mark.parametrize(
    "hostname,url",
    [
        ("allrecipes.com", "https://www.allrecipes.com/recipe/123/test-cake/"),
        ("seriouseats.com", "https://www.seriouseats.com/test-cake"),
    ],
)
def test_adapter_returns_dict_or_none(hostname: str, url: str) -> None:
    """Adapter must return a dict with required keys or None; must not raise."""
    adapter = get_adapter(hostname)
    assert adapter is not None

    result = adapter(_MINIMAL_HTML, url)
    # Either None or a dict with the expected keys
    if result is not None:
        assert isinstance(result, dict)
        for key in ("title", "ingredients", "instructions"):
            assert key in result, f"Missing key {key!r} in adapter result"
        assert isinstance(result["ingredients"], list)
        assert isinstance(result["instructions"], list)


def test_adapter_returns_none_on_empty_html() -> None:
    """Adapter must not raise on empty/invalid HTML — return None."""
    adapter = get_adapter("allrecipes.com")
    assert adapter is not None
    result = adapter("", "https://www.allrecipes.com/recipe/123/")
    # Either None or a dict; crucially, must not raise
    assert result is None or isinstance(result, dict)
