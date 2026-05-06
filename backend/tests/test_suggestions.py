"""Unit tests for the suggestion scoring engine."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from forkit.api.suggestions import score_recipe
from forkit.models import Recipe


class _FakeRecipe:
    """Lightweight stand-in for Recipe used in pure scoring unit tests."""

    def __init__(
        self,
        *,
        cook_count: int = 0,
        rating: int | None = 3,
        days_since_cooked: int | None = None,
        days_since_created: int = 30,
    ) -> None:
        now = datetime.now(timezone.utc)
        self.id = "test-id"
        self.title = "Test Recipe"
        self.hero_image_path = None
        self.total_time = None
        self.cuisine = None
        self.cook_count = cook_count
        self.rating = rating
        self.last_cooked: datetime | None = (
            now - timedelta(days=days_since_cooked) if days_since_cooked is not None else None
        )
        self.created_at: datetime = now - timedelta(days=days_since_created)


def _make_recipe(**kwargs) -> _FakeRecipe:  # type: ignore[return]
    return _FakeRecipe(**kwargs)


# ---------------------------------------------------------------------------
# Cold start
# ---------------------------------------------------------------------------

def test_cold_start_sorted_by_created_at(db_session):
    """When all cook_count == 0, suggestions are sorted newest first."""
    from forkit.api.suggestions import suggestions_tonight
    import asyncio

    now = datetime.now(timezone.utc)

    older = Recipe(
        title="Older Recipe",
        source_url="https://example.com/older",
        instructions=json.dumps(["Step 1"]),
        cook_count=0,
        created_at=now - timedelta(days=10),
        updated_at=now - timedelta(days=10),
    )
    newer = Recipe(
        title="Newer Recipe",
        source_url="https://example.com/newer",
        instructions=json.dumps(["Step 1"]),
        cook_count=0,
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
    )
    db_session.add_all([older, newer])
    db_session.commit()

    # Patch get_session dependency via overriding db_session
    from forkit.db import get_session
    from forkit.main import app

    def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override

    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        resp = client.get("/api/suggestions/tonight")

    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["cold_start"] is True
    assert data["tonight"] is not None
    assert data["tonight"]["title"] == "Newer Recipe"


# ---------------------------------------------------------------------------
# Score function unit tests (no DB required)
# ---------------------------------------------------------------------------

def test_score_higher_for_recent_addition():
    """A recipe created within 7 days gets a new_bonus bump."""
    now = datetime.now(timezone.utc)
    max_cook = 1

    new_recipe = _make_recipe(cook_count=1, days_since_cooked=5, days_since_created=3)
    old_recipe = _make_recipe(cook_count=1, days_since_cooked=5, days_since_created=60)

    score_new = score_recipe(new_recipe, now, max_cook)
    score_old = score_recipe(old_recipe, now, max_cook)

    assert score_new > score_old, "New recipe (within 7 days) should score higher"


def test_score_higher_for_recent_cook():
    """A recipe cooked recently scores higher on recency than one cooked long ago."""
    now = datetime.now(timezone.utc)
    max_cook = 5

    recently_cooked = _make_recipe(cook_count=5, days_since_cooked=1)
    long_ago_cooked = _make_recipe(cook_count=5, days_since_cooked=60)

    # Recency weight is 40%; recently cooked recipe should score higher
    score_recent = score_recipe(recently_cooked, now, max_cook)
    score_old = score_recipe(long_ago_cooked, now, max_cook)

    # Note: we want VARIETY, so lower recency = better score for suggestions
    # score uses 1/(days+1), meaning recently cooked DOES score higher on recency
    # The intent is "if cooked recently, still surfaces as trusted"
    # but variety is handled by the caller in production UI logic
    assert score_recent > score_old


def test_score_higher_for_higher_rating():
    """Higher rating increases score, all else equal."""
    now = datetime.now(timezone.utc)
    max_cook = 1

    high_rating = _make_recipe(cook_count=1, rating=5, days_since_cooked=30)
    low_rating = _make_recipe(cook_count=1, rating=1, days_since_cooked=30)

    assert score_recipe(high_rating, now, max_cook) > score_recipe(low_rating, now, max_cook)


def test_score_handles_never_cooked():
    """A recipe with no last_cooked date (days_since=9999) doesn't crash."""
    now = datetime.now(timezone.utc)
    r = _make_recipe(cook_count=0, days_since_cooked=None)
    score = score_recipe(r, now, max_cook=1)
    assert 0.0 <= score <= 1.5  # reasonable bounds


def test_score_handles_null_rating():
    """A recipe with rating=None defaults to rating=3 (mid) without error."""
    now = datetime.now(timezone.utc)
    r = _make_recipe(cook_count=2, rating=None, days_since_cooked=5)
    score = score_recipe(r, now, max_cook=2)
    assert score > 0.0


def test_suggestions_tonight_empty_db(db_session):
    """With no recipes, tonight=None and cold_start=True."""
    from forkit.db import get_session
    from forkit.main import app
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override

    with TestClient(app) as client:
        resp = client.get("/api/suggestions/tonight")

    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["tonight"] is None
    assert data["cold_start"] is True
    assert data["alternates"] == []


def test_suggestions_tonight_uses_score_when_cooked(db_session):
    """With cooked recipes, response is not cold_start and tonight is set."""
    now = datetime.now(timezone.utc)

    r1 = Recipe(
        title="Highly Rated",
        source_url="https://example.com/r1",
        instructions=json.dumps(["Step"]),
        cook_count=10,
        rating=5,
        last_cooked=now - timedelta(days=3),
        created_at=now - timedelta(days=30),
        updated_at=now - timedelta(days=3),
    )
    r2 = Recipe(
        title="Rarely Cooked",
        source_url="https://example.com/r2",
        instructions=json.dumps(["Step"]),
        cook_count=1,
        rating=2,
        last_cooked=now - timedelta(days=90),
        created_at=now - timedelta(days=120),
        updated_at=now - timedelta(days=90),
    )
    db_session.add_all([r1, r2])
    db_session.commit()

    from forkit.db import get_session
    from forkit.main import app
    from fastapi.testclient import TestClient

    def _override():
        yield db_session

    app.dependency_overrides[get_session] = _override

    with TestClient(app) as client:
        resp = client.get("/api/suggestions/tonight")

    app.dependency_overrides.clear()

    assert resp.status_code == 200
    data = resp.json()
    assert data["cold_start"] is False
    assert data["tonight"] is not None
