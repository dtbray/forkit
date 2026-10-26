import json

import pytest

from forkit.import_worker import load_config, run_worker


def test_load_config_deduplicates_and_rejects_unsafe_pacing(tmp_path):
    path = tmp_path / "sources.json"
    url = "https://recipes.example/category/vegan/"
    path.write_text(json.dumps({"sources": [url, url]}))
    assert load_config(path)["sources"] == [url]
    path.write_text(json.dumps({"sources": [url], "delay_seconds": 0}))
    with pytest.raises(ValueError):
        load_config(path)


async def test_worker_round_robins_sources_and_isolates_paused_source(monkeypatch):
    calls = []
    instances = []

    class FakeImporter:
        def __init__(self, url, delay):
            self.url = url
            self.last_request = 0
            self.db = type("DB", (), {"close": lambda self: None})()
            self.runs = 0
            instances.append(self)

        async def run(self, **kwargs):
            calls.append(self.url)
            self.runs += 1
            if self.url == "paused":
                raise RuntimeError("publisher paused")
            self.last_request += 5
            return {"source_url": self.url}

        def has_pending_work(self):
            return self.runs < 2

    monkeypatch.setattr("forkit.import_worker.CategoryImporter", FakeImporter)
    await run_worker(
        {"sources": ["first", "paused", "last"], "delay": 5, "batch": 10, "interval": 86400},
        once=True,
    )
    assert calls == ["first", "paused", "last", "first", "last"]
    assert instances[2].last_request >= instances[0].last_request


async def test_publisher_pause_stops_same_origin_including_prior_round_work(monkeypatch):
    from forkit.wordpress import ImportPaused

    calls = []
    instances = []
    first = "https://recipes.example/category/first/"
    paused = "https://recipes.example/category/paused/"
    sibling = "https://recipes.example:443/category/sibling/"
    other = "https://other.example/category/recipes/"

    class FakeImporter:
        def __init__(self, url, delay):
            self.url = url
            self.last_request = 0
            self.db = type("DB", (), {"close": lambda self: None})()
            self.runs = 0
            self.published = []
            instances.append(self)

        async def run(self, **kwargs):
            calls.append(self.url)
            self.runs += 1
            if self.url == paused:
                raise ImportPaused("Publisher returned HTTP 403; import paused")
            return {"source_url": self.url}

        def publish(self):
            self.published.append((self.stage, self.error))

        def has_pending_work(self):
            return self.runs < 2

    monkeypatch.setattr("forkit.import_worker.CategoryImporter", FakeImporter)
    await run_worker(
        {"sources": [first, paused, sibling, other], "delay": 5, "batch": 10, "interval": 86400},
        once=True,
    )
    assert calls == [first, paused, other, other]
    assert instances[0].published[0][0] == "paused"
    assert instances[2].published[0][0] == "paused"
    assert "403" in instances[2].published[0][1]
