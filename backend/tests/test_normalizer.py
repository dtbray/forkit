"""Normalizer tests — HTML sanitization (S2) and time normalization."""

from __future__ import annotations

import pytest

from forkit.parser.normalizer import normalize, _to_iso_duration


class TestSanitization:
    """bleach allowlist must strip disallowed HTML (S2)."""

    def test_strips_script_tag(self) -> None:
        raw = {
            "title": '<script>alert("xss")</script>Pasta',
            "description": None,
            "ingredients": [],
            "instructions": [],
        }
        result = normalize(raw)
        # bleach strip=True removes the tag; inner text is kept but that's safe —
        # no executable HTML remains.  The tag itself must be gone.
        assert "<script>" not in result["title"]
        assert "</script>" not in result["title"]
        assert "Pasta" in result["title"]

    def test_strips_iframe(self) -> None:
        raw = {
            "title": "Cake",
            "description": '<iframe src="evil.com"></iframe>Delicious',
            "ingredients": [],
            "instructions": [],
        }
        result = normalize(raw)
        assert "<iframe>" not in result["description"]
        assert "Delicious" in result["description"]

    def test_allows_basic_formatting(self) -> None:
        raw = {
            "title": "Soup",
            "description": "<strong>Rich</strong> broth",
            "ingredients": [],
            "instructions": ["<em>Stir</em> constantly"],
        }
        result = normalize(raw)
        assert "<strong>" in result["description"]
        assert "<em>" in result["instructions"][0]

    def test_strips_on_events(self) -> None:
        raw = {
            "title": 'Good Recipe<img onload="evil()" src="x">',
            "description": None,
            "ingredients": [],
            "instructions": [],
        }
        result = normalize(raw)
        assert "onload" not in result["title"]

    def test_ingredients_no_html(self) -> None:
        raw = {
            "title": "Test",
            "ingredients": ['<b>2</b> cups <script>x()</script>flour'],
            "instructions": [],
        }
        result = normalize(raw)
        # ingredients must be plain text
        assert "<b>" not in result["ingredients"][0]
        assert "<script>" not in result["ingredients"][0]
        assert "flour" in result["ingredients"][0]


class TestTimeNormalization:
    @pytest.mark.parametrize(
        "input_val,expected",
        [
            ("PT30M", "PT30M"),
            ("pt1h", "PT1H"),
            ("30", "PT30M"),
            ("30 minutes", "PT30M"),
            ("1 hour 15 minutes", "PT75M"),
            ("1 hr", "PT60M"),
            (None, None),
            ("", None),
            ("not a time", None),
        ],
    )
    def test_iso_duration(self, input_val: str | None, expected: str | None) -> None:
        result = _to_iso_duration(input_val)
        assert result == expected


class TestWhitespace:
    def test_strips_whitespace(self) -> None:
        raw = {
            "title": "  Pasta  ",
            "description": "  Good stuff.  ",
            "ingredients": ["  2 cups flour  "],
            "instructions": ["  Boil water.  "],
        }
        result = normalize(raw)
        assert result["title"] == "Pasta"
        assert result["description"] == "Good stuff."
        assert result["ingredients"][0] == "2 cups flour"
        assert result["instructions"][0] == "Boil water."
