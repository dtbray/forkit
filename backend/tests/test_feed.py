"""Tests for Phase 2 Feed Subscriber — GET /api/feed/inbox, POST /api/feed/promote,
POST /api/feed/dismiss.

All tests use FORKIT_DISABLE_SCHEDULER=1 (set in conftest.py) to prevent the
APScheduler from starting during tests.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from forkit.main import app
from forkit.db import get_session
from forkit.models.discovery_site import DiscoverySite
from forkit.models.feed_item import FeedItem
from forkit.models.recipe import Recipe


def _make_site(session) -> DiscoverySite:
    """Insert a minimal discovery_site for feed tests."""
    site = DiscoverySite(
        id=str(uuid.uuid4()),
        slug="test-feed-site",
        name="Test Feed Site",
        home_url="https://example.com",
        adapter_kind="feed_only",
        adapter_config_json='{"feed_url": "https://example.com/feed.rss"}',
        search_enabled=0,
        feed_enabled=1,
        is_builtin=0,
    )
    session.add(site)
    session.commit()
    return site


def _make_feed_item(session, site: DiscoverySite, **overrides) -> FeedItem:
    """Insert a feed_item for tests."""
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=str(uuid.uuid4()),
        site_id=site.id,
        entry_guid=str(uuid.uuid4()),
        url="https://example.com/recipe/1",
        title="Test Recipe",
        summary="A delicious test recipe.",
        published_at=now,
        ingested=0,
        dismissed=0,
        created_at=now,
    )
    defaults.update(overrides)
    item = FeedItem(**defaults)
    session.add(item)
    session.commit()
    return item


def _make_client(db_session) -> TestClient:
    """Build a TestClient with the per-test DB session injected."""
    app.dependency_overrides[get_session] = lambda: db_session
    client = TestClient(app, raise_server_exceptions=True)
    return client


# ---------------------------------------------------------------------------
# GET /api/feed/inbox
# ---------------------------------------------------------------------------


def test_inbox_returns_200_with_correct_shape(db_session) -> None:
    """Inbox must return 200 with items list, page, limit, total."""
    site = _make_site(db_session)
    _make_feed_item(db_session, site)

    client = _make_client(db_session)
    try:
        resp = client.get("/api/feed/inbox")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "page" in data
        assert "limit" in data
        assert "total" in data
        assert data["total"] >= 1
        item = data["items"][0]
        for field in ("id", "site_id", "site_name", "url", "title", "ingested", "dismissed"):
            assert field in item, f"Missing field {field!r} in inbox item"
    finally:
        app.dependency_overrides.pop(get_session, None)


def _make_recipe(session) -> Recipe:
    """Insert a minimal Recipe row for FK-safe tests."""
    now = datetime.now(timezone.utc)
    recipe = Recipe(
        id=str(uuid.uuid4()),
        title="Test Recipe",
        source_url=f"https://example.com/recipe/{uuid.uuid4()}",
        instructions="[]",
        parser_source="jsonld",
        parser_confidence=1.0,
        created_at=now,
        updated_at=now,
    )
    session.add(recipe)
    session.commit()
    return recipe


def test_inbox_excludes_ingested_items(db_session) -> None:
    """Ingested feed items must not appear in inbox."""
    site = _make_site(db_session)
    recipe = _make_recipe(db_session)
    _make_feed_item(db_session, site, ingested=1, recipe_id=recipe.id)

    client = _make_client(db_session)
    try:
        resp = client.get("/api/feed/inbox")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_inbox_excludes_dismissed_items(db_session) -> None:
    """Dismissed feed items must not appear in inbox."""
    site = _make_site(db_session)
    _make_feed_item(db_session, site, dismissed=1)

    client = _make_client(db_session)
    try:
        resp = client.get("/api/feed/inbox")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
    finally:
        app.dependency_overrides.pop(get_session, None)


# ---------------------------------------------------------------------------
# POST /api/feed/promote
# ---------------------------------------------------------------------------


def test_promote_marks_feed_item_ingested_and_returns_recipe_id(db_session) -> None:
    """Promote must mark feed_item.ingested=1 and return recipe_id."""
    site = _make_site(db_session)
    item = _make_feed_item(db_session, site)
    # Pre-create the recipe row so the FK constraint on recipe_id is satisfied
    recipe = _make_recipe(db_session)

    client = _make_client(db_session)
    try:
        with patch(
            "forkit.api.feed.ingest_url",
            new=AsyncMock(return_value={"recipe_id": recipe.id, "parser_source": "jsonld", "parser_confidence": 1.0}),
        ):
            resp = client.post("/api/feed/promote", json={"feed_item_id": item.id})

        assert resp.status_code == 200
        data = resp.json()
        assert data["feed_item_id"] == item.id
        assert data["recipe_id"] == recipe.id

        # Verify DB state
        db_session.expire(item)
        db_session.refresh(item)
        assert item.ingested == 1
        assert item.recipe_id == recipe.id
        assert item.ingested_at is not None
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_promote_idempotent(db_session) -> None:
    """Promoting the same feed_item twice must be idempotent."""
    site = _make_site(db_session)
    recipe = _make_recipe(db_session)
    item = _make_feed_item(
        db_session, site, ingested=1, recipe_id=recipe.id
    )
    existing_recipe_id = recipe.id

    client = _make_client(db_session)
    try:
        # Second promote — ingest_url should NOT be called
        with patch(
            "forkit.api.feed.ingest_url",
            new=AsyncMock(side_effect=Exception("should not be called")),
        ):
            resp = client.post("/api/feed/promote", json={"feed_item_id": item.id})

        assert resp.status_code == 200
        data = resp.json()
        assert data["recipe_id"] == existing_recipe_id
        assert data["already_existed"] is True
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_promote_404_on_missing_item(db_session) -> None:
    """Promote with a non-existent feed_item_id must return 404."""
    client = _make_client(db_session)
    try:
        resp = client.post("/api/feed/promote", json={"feed_item_id": str(uuid.uuid4())})
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_session, None)


# ---------------------------------------------------------------------------
# POST /api/feed/dismiss
# ---------------------------------------------------------------------------


def test_dismiss_marks_dismissed(db_session) -> None:
    """Dismiss must set feed_item.dismissed=1."""
    site = _make_site(db_session)
    item = _make_feed_item(db_session, site)

    client = _make_client(db_session)
    try:
        resp = client.post("/api/feed/dismiss", json={"feed_item_id": item.id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["feed_item_id"] == item.id
        assert data["dismissed"] is True

        db_session.expire(item)
        db_session.refresh(item)
        assert item.dismissed == 1
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_dismiss_404_on_missing_item(db_session) -> None:
    """Dismiss with a non-existent feed_item_id must return 404."""
    client = _make_client(db_session)
    try:
        resp = client.post("/api/feed/dismiss", json={"feed_item_id": str(uuid.uuid4())})
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_session, None)
