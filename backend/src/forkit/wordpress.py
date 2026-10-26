"""Paced, resumable WordPress category imports. Run with python -m forkit.wordpress."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import gzip
import hashlib
import json
import sqlite3
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from fastapi import HTTPException

from .config import get_settings
from .models import Recipe
from .parser.fetcher import FetchError, safe_fetch
from .parser.images import store_image_bytes
from .parser.jsonld import extract_jsonld
from .services.ingest import ingest_url

USER_AGENT = "ForkitCategoryImporter/0.1 (+https://github.com/dtbray/forkit)"


class ImportPaused(Exception):
    """Stop a run when a publisher blocks requests or asks for a long pause."""


def source_location(category_url: str) -> tuple[str, str, str]:
    parts = urlsplit(category_url)
    if (
        parts.scheme not in {"https", "http"}
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        raise ValueError("Use an http(s) WordPress category URL without credentials")
    prefix, marker, tail = parts.path.partition("/category/")
    if not marker or not tail.strip("/") or parts.query or parts.fragment:
        raise ValueError("Expected a WordPress /category/.../slug/ URL")
    category_url = urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") + "/", "", ""))
    base = urlunsplit((parts.scheme, parts.netloc, prefix, "", ""))
    return category_url, base, tail.strip("/").split("/")[-1]


def canonical_url(url: str, base: str) -> str:
    p, origin = urlsplit(url), urlsplit(base)
    if p.scheme != origin.scheme or p.netloc != origin.netloc or p.username or p.password:
        raise ValueError("Post URL must stay on the configured WordPress origin")
    if not p.path.startswith(origin.path.rstrip("/") + "/"):
        raise ValueError("Post URL is outside the configured WordPress installation")
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def retry_seconds(value: str | None, attempt: int) -> float:
    try:
        return max(0, float(value))
    except (TypeError, ValueError):
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 30 * (2**attempt)


class CategoryImporter:
    def __init__(
        self,
        category_url: str,
        *,
        state_root: Path | None = None,
        delay: float = 5,
        session_factory=None,
    ) -> None:
        self.url, self.base, self.slug = source_location(category_url)
        self.delay = max(2, delay)
        self.last_request = 0.0
        self.robots: RobotFileParser | None = None
        self.session_factory = session_factory
        key = hashlib.sha256(self.url.encode()).hexdigest()[:24]
        root = state_root or Path(get_settings().forkit_cache_dir).parent / "imports"
        self.directory = root / key
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.directory / "state.sqlite")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS image_jobs (
                recipe_id TEXT PRIMARY KEY, status TEXT NOT NULL, error TEXT);
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS items (
                post_id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE,
                modified TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                recipe_id TEXT, error TEXT);
        """)
        self.stage = "idle"
        self.error: str | None = None
        self.images_enabled = True

    def meta(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))

    def status(self) -> dict:
        counts = dict(self.db.execute("SELECT status, count(*) FROM items GROUP BY status"))
        return {
            "source_url": self.url,
            "name": self.meta("name", self.slug),
            "stage": self.stage,
            "total": sum(counts.values()),
            "counts": counts,
            "images": dict(
                self.db.execute("SELECT status, count(*) FROM image_jobs GROUP BY status")
            ),
            "error": self.error,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    def publish(self) -> None:
        target = self.directory / "status.json"
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.status()))
        tmp.replace(target)

    async def fetch(
        self, url: str, *, check_robots: bool = True, max_bytes: int = 5 * 1024 * 1024
    ) -> tuple[bytes, dict]:
        if check_robots and self.robots and not self.robots.can_fetch(USER_AGENT, url):
            raise ImportPaused(f"robots.txt disallows {url}")
        for attempt in range(4):
            await asyncio.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            headers: dict[str, str] = {}
            try:
                body = await safe_fetch(
                    url, user_agent=USER_AGENT, response_headers=headers, max_bytes=max_bytes
                )
                return body, headers
            except (FetchError, httpx.HTTPError) as exc:
                status = getattr(exc, "status_code", None)
                if status in {401, 403}:
                    raise ImportPaused(f"Publisher returned HTTP {status}; import paused") from exc
                if status is not None and status != 429 and status < 500:
                    raise
                if attempt == 3:
                    raise ImportPaused(f"Repeated upstream failure: {exc}") from exc
                wait = retry_seconds(getattr(exc, "retry_after", None), attempt)
                if wait > 3600:
                    raise ImportPaused("Publisher requested a pause exceeding one hour") from exc
                self.stage = "backoff"
                self.publish()
                await asyncio.sleep(max(self.delay, wait))
        raise AssertionError("unreachable")

    async def load_robots(self) -> None:
        origin = urlsplit(self.base)
        url = urlunsplit((origin.scheme, origin.netloc, "/robots.txt", "", ""))
        try:
            body, _ = await self.fetch(url, check_robots=False)
        except FetchError as exc:
            if exc.status_code != 404:
                raise
            body = b"User-agent: *\nAllow: /"
        self.robots = RobotFileParser(url)
        self.robots.parse(body.decode("utf-8", errors="replace").splitlines())
        self.delay = max(self.delay, self.robots.crawl_delay(USER_AGENT) or 0)

    async def discover(self, *, refresh: bool = False) -> None:
        if self.meta("discovered") and not refresh:
            return
        self.stage = "discovering"
        self.publish()
        if refresh:
            self.set_meta("next_page", "1")
            self.set_meta("discovered", "")
            self.db.commit()
        if not self.meta("category_id"):
            endpoint = (
                self.base
                + "/wp-json/wp/v2/categories?"
                + urlencode({"slug": self.slug, "_fields": "id,link,name,count"})
            )
            body, _ = await self.fetch(endpoint)
            matches = [
                x for x in json.loads(body) if x.get("link", "").rstrip("/") == self.url.rstrip("/")
            ]
            if len(matches) != 1:
                raise ValueError(
                    "Category URL did not resolve to one matching public WordPress category"
                )
            self.set_meta("category_id", str(matches[0]["id"]))
            self.set_meta("name", matches[0]["name"])
            self.db.commit()
        page = int(self.meta("next_page", "1"))
        while page <= 1000:
            endpoint = (
                self.base
                + "/wp-json/wp/v2/posts?"
                + urlencode(
                    {
                        "categories": self.meta("category_id"),
                        "per_page": 100,
                        "page": page,
                        "orderby": "id",
                        "order": "asc",
                        "_fields": "id,link,modified_gmt,categories",
                    }
                )
            )
            body, headers = await self.fetch(endpoint)
            posts = json.loads(body)
            if not isinstance(posts, list):
                raise ValueError("WordPress returned an invalid post collection")
            # Page checkpoint and candidates commit together. Never follow off-site links.
            with self.db:
                for post in posts:
                    url = canonical_url(post["link"], self.base)
                    self.db.execute(
                        """INSERT INTO items(post_id,url,modified) VALUES(?,?,?)
                        ON CONFLICT(post_id) DO UPDATE SET
                        status=CASE WHEN items.modified != excluded.modified AND items.status IN
                          ('imported','existing','changed') THEN 'changed'
                          WHEN items.modified != excluded.modified THEN 'pending'
                          ELSE items.status END,
                        modified=excluded.modified, url=excluded.url""",
                        (post["id"], url, post.get("modified_gmt", "")),
                    )
                self.set_meta("next_page", str(page + 1))
                total_pages = int(headers.get("x-wp-totalpages", "0"))
                done = len(posts) < 100 or (total_pages and page >= total_pages)
                if done:
                    self.set_meta("discovered", datetime.now(UTC).isoformat())
            self.publish()
            if done:
                return
            page += 1
        raise ValueError("Discovery exceeded the 1000-page safety limit")

    async def ensure_image(self, row, recipe: Recipe, session) -> None:
        if not self.images_enabled:
            return
        if recipe.hero_image_path:
            with self.db:
                self.db.execute(
                    "INSERT OR REPLACE INTO image_jobs VALUES (?, 'existing', NULL)", (recipe.id,)
                )
            return
        done = self.db.execute(
            "SELECT status FROM image_jobs WHERE recipe_id=?", (recipe.id,)
        ).fetchone()
        if done and done[0] in {"saved", "missing", "failed"}:
            return
        try:
            version = hashlib.sha256(row["modified"].encode()).hexdigest()[:12]
            filename = f"{row['post_id']}-{version}.html.gz"
            cache = self.directory / filename
            # Reuse the same post's cached page from another category on this site.
            if not cache.exists():
                for candidate in self.directory.parent.glob(f"*/{filename}"):
                    status_file = candidate.parent / "status.json"
                    if status_file.exists():
                        source = json.loads(status_file.read_text()).get("source_url", "")
                        if source_location(source)[1] == self.base:
                            cache = candidate
                            break
            if cache.exists():
                html = gzip.decompress(cache.read_bytes())
            else:
                html, _ = await self.fetch(row["url"])
                cache.write_bytes(gzip.compress(html))
            raw = extract_jsonld(
                html.decode("utf-8", errors="replace"), row["url"], schema_only=True
            )
            image_url = raw.get("image_url") if raw else None
            if not image_url:
                outcome, error = "missing", None
            else:
                canonical_url(
                    image_url, self.base
                )  # Keep image requests on the publisher's origin.
                data, _ = await self.fetch(image_url, max_bytes=10 * 1024 * 1024)
                path = store_image_bytes(data, get_settings().forkit_image_dir)
                if path is None:
                    raise ValueError("Image could not be decoded or stored")
                recipe.hero_image_path = path
                session.commit()
                outcome, error = "saved", None
        except ImportPaused:
            raise
        except Exception as exc:
            session.rollback()
            outcome, error = "failed", str(exc)[:500]
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO image_jobs VALUES (?, ?, ?)", (recipe.id, outcome, error)
            )

    async def backfill_images(
        self, *, limit: int | None = None, retry_failed: bool = False
    ) -> None:
        if not self.images_enabled:
            return
        if self.session_factory is None:
            from .db import SessionLocal

            self.session_factory = SessionLocal
        if retry_failed:
            self.db.execute("DELETE FROM image_jobs WHERE status='failed'")
            self.db.commit()
        rows = self.db.execute(
            "SELECT * FROM items WHERE status IN ('imported','existing') ORDER BY post_id DESC"
        ).fetchall()
        for row in rows[:limit] if limit else rows:
            with self.session_factory() as session:
                recipe = session.query(Recipe).filter_by(source_url=row["url"]).first()
                if recipe:
                    self.stage = "images"
                    self.publish()
                    await self.ensure_image(row, recipe, session)
            self.publish()

    async def import_pending(self, *, limit: int | None = None, retry_failed: bool = False) -> None:
        if self.session_factory is None:
            from .db import SessionLocal

            self.session_factory = SessionLocal
        if retry_failed:
            self.db.execute("UPDATE items SET status='pending' WHERE status='failed'")
            self.db.commit()
        query = "SELECT * FROM items WHERE status='pending' ORDER BY post_id LIMIT ?"
        for row in self.db.execute(query, (limit if limit is not None else -1,)).fetchall():
            self.stage = "importing"
            self.publish()
            with self.session_factory() as session:
                existing = session.query(Recipe).filter_by(source_url=row["url"]).first()
                if existing:
                    await self.ensure_image(row, existing, session)
                    self.record(row["post_id"], "existing", existing.id)
                    continue
                version = hashlib.sha256(row["modified"].encode()).hexdigest()[:12]
                cache = self.directory / f"{row['post_id']}-{version}.html.gz"
                try:
                    if cache.exists():
                        html = gzip.decompress(cache.read_bytes())
                    else:
                        html, _ = await self.fetch(row["url"])
                        tmp = cache.with_suffix(".tmp")
                        tmp.write_bytes(gzip.compress(html))
                        tmp.replace(cache)
                    result = await ingest_url(
                        row["url"],
                        session,
                        html_bytes=html,
                        structured_only=True,
                        download_images=False,
                    )
                    await self.ensure_image(row, session.get(Recipe, result["recipe_id"]), session)
                    self.record(row["post_id"], "imported", result["recipe_id"])
                except ImportPaused:
                    raise
                except Exception as exc:
                    session.rollback()
                    if isinstance(exc, HTTPException) and exc.status_code == 409:
                        self.record(row["post_id"], "existing")
                    elif isinstance(exc, HTTPException) and exc.status_code == 422:
                        self.record(row["post_id"], "skipped", error=str(exc.detail))
                    else:
                        self.record(row["post_id"], "failed", error=str(exc)[:500])
            self.publish()

    def record(
        self, post_id: int, status: str, recipe_id: str | None = None, error: str | None = None
    ) -> None:
        with self.db:
            self.db.execute(
                "UPDATE items SET status=?, recipe_id=?, error=? WHERE post_id=?",
                (status, recipe_id, error, post_id),
            )

    async def run(
        self, *, refresh: bool = False, limit: int | None = None, retry_failed: bool = False
    ) -> dict:
        # Per-source lock prevents CLI and worker from importing concurrently.
        with (self.directory / "worker.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                self.error = None
                await self.load_robots()
                await self.discover(refresh=refresh)
                await self.backfill_images(limit=limit, retry_failed=retry_failed)
                await self.import_pending(limit=limit, retry_failed=retry_failed)
                self.stage = "idle" if self.status()["counts"].get("pending", 0) else "complete"
            except Exception as exc:
                self.stage, self.error = "paused", str(exc)[:500]
                raise
            finally:
                self.publish()
        return self.status()


async def main_async(args: argparse.Namespace) -> int:
    importer = CategoryImporter(args.category_url, delay=args.delay)
    importer.images_enabled = not args.no_images
    while True:
        try:
            result = await importer.run(
                refresh=args.refresh, limit=args.limit, retry_failed=args.retry_failed
            )
            print(json.dumps(result), flush=True)
        except Exception as exc:
            print(json.dumps({"error": str(exc), **importer.status()}), flush=True)
            if not args.interval:
                return 1
        if not args.interval:
            return 0
        await asyncio.sleep(max(300, args.interval))
        args.refresh = True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("category_url")
    parser.add_argument(
        "--delay", type=float, default=5, help="Seconds between requests (minimum 2)"
    )
    parser.add_argument("--limit", type=int, help="Maximum candidate recipes to process this run")
    parser.add_argument("--no-images", action="store_true", help="Skip recipe image downloads")
    parser.add_argument("--refresh", action="store_true", help="Refresh the category manifest")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument(
        "--interval", type=int, default=0, help="Repeat interval in seconds; zero runs once"
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
