import json
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy.orm import sessionmaker

from forkit.models import Recipe
from forkit.parser.fetcher import FetchError
from forkit.wordpress import (
    CategoryImporter,
    ImportPaused,
    canonical_url,
    retry_seconds,
    source_location,
)

URL = "https://recipes.example/category/recipes/vegetarian/"
BASE = "https://recipes.example"
HTML = b"""<script type="application/ld+json">{"@type":"Recipe","name":"Test lentils",
"recipeIngredient":["1 cup lentils"],"recipeInstructions":[{"@type":"HowToSection",
"itemListElement":[{"@type":"HowToStep","text":"Cook the lentils."}]}]}</script>"""


@pytest.fixture
def importer(tmp_path, db_engine, monkeypatch):
    monkeypatch.setattr("forkit.wordpress.asyncio.sleep", AsyncMock())
    instance = CategoryImporter(
        URL, state_root=tmp_path, session_factory=sessionmaker(bind=db_engine)
    )
    yield instance
    instance.db.close()


def fake_site(monkeypatch, posts=None, html=HTML):
    posts = (
        posts
        if posts is not None
        else [{"id": 1, "link": BASE + "/lentils/", "modified_gmt": "2026-10-25T12:00:00"}]
    )
    calls = []

    async def fetch(url, **kwargs):
        calls.append(url)
        if url.endswith("/robots.txt"):
            return b"User-agent: *\nAllow: /\nCrawl-delay: 7"
        if "/categories?" in url:
            return json.dumps([{"id": 7, "link": URL, "name": "Vegetarian"}]).encode()
        if "/posts?" in url:
            kwargs["response_headers"]["x-wp-totalpages"] = "1"
            return json.dumps(posts).encode()
        return html

    monkeypatch.setattr("forkit.wordpress.safe_fetch", fetch)
    return calls


async def test_import_and_resume_without_refetch(importer, monkeypatch, db_session):
    calls = fake_site(monkeypatch)
    monkeypatch.setattr(
        "forkit.services.ingest._get_llm_provider", lambda _: pytest.fail("LLM forbidden")
    )
    result = await importer.run()
    assert result["counts"] == {"imported": 1}
    assert importer.delay == 7
    recipe = db_session.query(Recipe).one()
    assert recipe.source_url == BASE + "/lentils/"
    assert recipe.ingredients[0].raw_text == "1 cup lentils"
    assert json.loads(recipe.instructions)[0]["text"] == "Cook the lentils."
    assert recipe.parser_source == "jsonld"
    await importer.run()
    assert calls.count(BASE + "/lentils/") == 1
    assert len([c for c in calls if "/posts?" in c]) == 1
    status = json.loads((importer.directory / "status.json").read_text())
    assert status["stage"] == "complete"


async def test_non_recipe_skipped_without_llm(importer, monkeypatch):
    fake_site(monkeypatch, html=b"<html><h1>A collection of recipes</h1></html>")
    monkeypatch.setattr(
        "forkit.services.ingest._get_llm_provider", lambda _: pytest.fail("LLM forbidden")
    )
    result = await importer.run()
    assert result["counts"] == {"skipped": 1}


async def test_manifest_checkpoint_survives_failed_page(importer, monkeypatch):
    calls = []
    first = [{"id": n, "link": f"{BASE}/recipe-{n}/", "modified_gmt": "v1"} for n in range(1, 101)]

    async def fetch(url, **kwargs):
        calls.append(url)
        if "/categories?" in url:
            return json.dumps([{"id": 7, "link": URL, "name": "Vegetarian"}]).encode(), {}
        page = int(parse_qs(urlsplit(url).query)["page"][0])
        if page == 2 and len(calls) == 3:
            raise ImportPaused("temporary failure")
        return json.dumps(first if page == 1 else []).encode(), {"x-wp-totalpages": "2"}

    monkeypatch.setattr(importer, "fetch", fetch)
    with pytest.raises(ImportPaused):
        await importer.discover()
    assert importer.meta("next_page") == "2"
    assert importer.db.execute("select count(*) from items").fetchone()[0] == 100
    await importer.discover()
    assert importer.meta("discovered")
    assert len([u for u in calls if "page=1&" in u]) == 1


async def test_refresh_flags_changes_and_preserves_user_edits(importer, monkeypatch, db_session):
    fake_site(monkeypatch)
    await importer.run()
    recipe = db_session.query(Recipe).one()
    recipe.user_notes = "Use less salt"
    db_session.commit()
    calls = fake_site(
        monkeypatch, posts=[{"id": 1, "link": BASE + "/lentils/", "modified_gmt": "new-version"}]
    )
    result = await importer.run(refresh=True)
    assert result["counts"] == {"changed": 1}
    assert BASE + "/lentils/" not in calls
    db_session.expire_all()
    assert db_session.query(Recipe).one().user_notes == "Use less salt"


async def test_existing_recipe_recovers_after_checkpoint_failure(importer, monkeypatch, db_session):
    fake_site(monkeypatch)
    await importer.run()
    importer.db.execute("update items set status='pending', recipe_id=NULL")
    importer.db.commit()
    calls = fake_site(monkeypatch)
    result = await importer.run()
    assert result["counts"] == {"existing": 1}
    assert calls == [BASE + "/robots.txt"]
    assert db_session.query(Recipe).count() == 1


async def test_forbidden_stops_run_leaves_candidate_pending(importer, monkeypatch):
    fake_site(monkeypatch)
    await importer.load_robots()
    await importer.discover()

    async def forbidden(*args, **kwargs):
        raise FetchError("HTTP 403", status_code=403)

    monkeypatch.setattr("forkit.wordpress.safe_fetch", forbidden)
    with pytest.raises(ImportPaused):
        await importer.run()
    assert importer.db.execute("select status from items").fetchone()[0] == "pending"
    assert json.loads((importer.directory / "status.json").read_text())["stage"] == "paused"


async def test_robots_disallow_prevents_api_fetch(importer, monkeypatch):
    calls = []

    async def robots_only(url, **kwargs):
        calls.append(url)
        return b"User-agent: *\nDisallow: /wp-json/"

    monkeypatch.setattr("forkit.wordpress.safe_fetch", robots_only)
    with pytest.raises(ImportPaused, match=r"robots\.txt"):
        await importer.run()
    assert calls == [BASE + "/robots.txt"]


async def test_rate_limit_respects_retry_after(importer, monkeypatch):
    fetch = AsyncMock(
        side_effect=[FetchError("HTTP 429", status_code=429, retry_after="120"), b"ok"]
    )
    monkeypatch.setattr("forkit.wordpress.safe_fetch", fetch)
    assert (await importer.fetch(BASE + "/lentils/"))[0] == b"ok"
    from forkit.wordpress import asyncio

    assert any(call.args == (120,) for call in asyncio.sleep.call_args_list)
    assert fetch.call_count == 2


def test_reject_external_links_and_malformed_sources():
    with pytest.raises(ValueError):
        canonical_url("https://evil.example/recipe", BASE)
    with pytest.raises(ValueError):
        source_location("file:///category/vegetarian/")
    with pytest.raises(ValueError):
        source_location(URL + "?page=2")
    assert canonical_url(BASE + "/lentils/?utm_source=x#recipe", BASE) == BASE + "/lentils/"
    assert retry_seconds("45", 0) == 45
    assert retry_seconds(None, 2) == 120


async def test_second_worker_does_not_overwrite_active_status(importer, monkeypatch):
    import fcntl

    fake_site(monkeypatch)
    await importer.run()
    before = (importer.directory / "status.json").read_text()
    with (importer.directory / "worker.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            await importer.run()
    assert (importer.directory / "status.json").read_text() == before


def photo_bytes():
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (1800, 1300), "orange").save(out, "JPEG")
    return out.getvalue()


async def test_image_backfill_uses_cached_page_and_survives_resume(
    importer, monkeypatch, db_session, tmp_path
):
    from PIL import Image

    from forkit import wordpress
    from forkit.config import get_settings

    monkeypatch.setattr(get_settings(), "forkit_image_dir", str(tmp_path / "images"))
    html = HTML.replace(
        b'"@type":"Recipe"', b'"image":"https://recipes.example/photo.jpg","@type":"Recipe"'
    )
    calls = fake_site(monkeypatch, html=html)
    original_fetch = wordpress.safe_fetch

    async def fetch(url, **kwargs):
        if url.endswith("/photo.jpg"):
            calls.append(url)
            return photo_bytes()
        return await original_fetch(url, **kwargs)

    monkeypatch.setattr(wordpress, "safe_fetch", fetch)
    importer.images_enabled = False
    await importer.run()
    assert db_session.query(Recipe).one().hero_image_path is None
    importer.images_enabled = True
    await importer.run()
    db_session.expire_all()
    path = db_session.query(Recipe).one().hero_image_path
    assert path and path.endswith("/hero.webp")
    assert calls.count(BASE + "/lentils/") == 1
    assert calls.count(BASE + "/photo.jpg") == 1
    hero = Image.open(tmp_path / "images" / path)
    assert max(hero.size) <= 1600
    assert not hero.getexif()
    assert (tmp_path / "images" / path.replace("hero.webp", "thumb.webp")).exists()
    await importer.run()
    assert calls.count(BASE + "/photo.jpg") == 1


async def test_failed_image_is_nonfatal_and_retried_explicitly(importer, monkeypatch, tmp_path):
    from forkit import wordpress
    from forkit.config import get_settings

    monkeypatch.setattr(get_settings(), "forkit_image_dir", str(tmp_path / "images"))
    html = HTML.replace(
        b'"@type":"Recipe"', b'"image":"https://recipes.example/photo.jpg","@type":"Recipe"'
    )
    fake_site(monkeypatch, html=html)
    original_fetch = wordpress.safe_fetch
    attempts = 0

    async def fetch(url, **kwargs):
        nonlocal attempts
        if url.endswith("/photo.jpg"):
            attempts += 1
            if attempts == 1:
                raise FetchError("image missing", status_code=404)
            return photo_bytes()
        return await original_fetch(url, **kwargs)

    monkeypatch.setattr(wordpress, "safe_fetch", fetch)
    result = await importer.run()
    assert result["counts"] == {"imported": 1}
    assert result["images"] == {"failed": 1}
    await importer.run()
    assert attempts == 1
    result = await importer.run(retry_failed=True)
    assert attempts == 2
    assert result["images"] == {"saved": 1}


async def test_other_category_reuses_cached_page_and_recipe(
    importer, monkeypatch, tmp_path, db_engine, db_session
):
    from forkit import wordpress
    from forkit.config import get_settings

    monkeypatch.setattr(get_settings(), "forkit_image_dir", str(tmp_path / "images"))
    html = HTML.replace(
        b'"@type":"Recipe"', b'"image":"https://recipes.example/photo.jpg","@type":"Recipe"'
    )
    calls = fake_site(monkeypatch, html=html)
    importer.images_enabled = False
    await importer.run()
    original_fetch = wordpress.safe_fetch

    async def fetch(url, **kwargs):
        if url.endswith("/photo.jpg"):
            calls.append(url)
            return photo_bytes()
        return await original_fetch(url, **kwargs)

    monkeypatch.setattr(wordpress, "safe_fetch", fetch)
    other = CategoryImporter(
        BASE + "/category/vegan/", state_root=tmp_path, session_factory=sessionmaker(bind=db_engine)
    )
    other.set_meta("discovered", "yes")
    other.db.execute(
        "INSERT INTO items(post_id,url,modified) VALUES(1,?,?)",
        (BASE + "/lentils/", "2026-10-25T12:00:00"),
    )
    other.db.commit()
    result = await other.run()
    assert result["counts"] == {"existing": 1}
    assert calls.count(BASE + "/lentils/") == 1
    assert calls.count(BASE + "/photo.jpg") == 1
    db_session.expire_all()
    assert db_session.query(Recipe).count() == 1
    assert db_session.query(Recipe).one().hero_image_path
    other.db.close()
