"""DatasetAdapter — queries the local FTS5 community recipe corpus.

ADR-003 / Security sign-off 2026-05-12.

Security conditions enforced:
  Q2.1 — simple-query mode: escape `"` -> `""`, wrap whole input in double quotes.
  Q2.3 — input capped at 200 chars and 16 tokens.
  Q2.4 — FTS5 parse errors return [] with WARN log; never propagate as 5xx.
  Q2.6 — 500ms per-query timeout via interrupt() in a watchdog thread.
  Q3.1 — closed registry: only `internal://dataset/` is recognized.
  Q3.2 — exact-match regex `^internal://dataset/[1-9][0-9]{0,9}$`, int <= 2^31-1.
  Q3.5 — read-only handle opened with `?mode=ro&immutable=1`.
  Q4.5 — image_url validated as http/https; reject javascript:/data:/file:.

Note for frontend (per security sign-off Q3.3): `url` fields whose scheme is
`internal://` MUST be rendered as a non-anchor element (button/span) that
POSTs to the import endpoint with `external_id` only — NEVER as <a href>.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import uuid
from pathlib import Path
from urllib.parse import urlparse

import structlog

from ..discovery.schemas import RecipeStub, SourceSite
from .db import open_readonly

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Security-critical constants
# ---------------------------------------------------------------------------

MAX_QUERY_CHARS = 200  # Q2.3
MAX_QUERY_TOKENS = 16  # Q2.3
QUERY_TIMEOUT_MS = 500  # Q2.6
SQLITE_INT_MAX = 2_147_483_647  # Q3.2

# Q3.2: exact-match grammar for internal://dataset/<row_id>.
# `^[1-9][0-9]{0,9}$` for row_id: positive integer, max 10 digits, no leading zeros.
_INTERNAL_URL_RE = re.compile(r"^internal://dataset/([1-9][0-9]{0,9})$")

# Q4.5: URL scheme allowlist for stored URL fields surfaced to clients.
_PUBLIC_URL_SCHEMES = {"http", "https"}


def _build_match_expression(q: str) -> str:
    """Build a safe FTS5 MATCH expression from arbitrary user input.

    Simple-query mode per Security Condition Q2.1:
      - escape each `"` by doubling (`""`)
      - wrap the whole string in double quotes
      - this sidesteps FTS5 operator parsing entirely

    Caps per Q2.3:
      - 200 chars
      - 16 tokens (whitespace-delimited)
    """
    if not q:
        return '""'
    q = q.strip()[:MAX_QUERY_CHARS]
    tokens = q.split()
    if len(tokens) > MAX_QUERY_TOKENS:
        tokens = tokens[:MAX_QUERY_TOKENS]
    truncated = " ".join(tokens)
    escaped = truncated.replace('"', '""')
    return f'"{escaped}"'


def parse_internal_dataset_url(url: str) -> int:
    """Parse `internal://dataset/<row_id>` -> int.

    Security Condition Q3.2: exact-match regex; reject any URL with query
    string, fragment, port, or authority component. Integer must be <= 2^31-1.

    Raises ValueError on any deviation.
    """
    if not isinstance(url, str):
        raise ValueError("internal URL must be a string")
    m = _INTERNAL_URL_RE.match(url)
    if m is None:
        raise ValueError(f"invalid internal URL: {url!r}")
    row_id = int(m.group(1))
    if row_id <= 0 or row_id > SQLITE_INT_MAX:
        raise ValueError(f"internal URL row_id out of range: {row_id}")
    return row_id


def _validate_public_url(url: str | None) -> str | None:
    """Validate an http/https URL; return None if invalid. Q4.5."""
    if not url:
        return None
    parsed = urlparse(url.strip())
    if parsed.scheme not in _PUBLIC_URL_SCHEMES or not parsed.netloc:
        return None
    return url.strip()


class _SqliteWatchdog:
    """Per-query timeout via sqlite3.Connection.interrupt() — Q2.6."""

    def __init__(self, conn: sqlite3.Connection, timeout_ms: int) -> None:
        self._conn = conn
        self._timeout = timeout_ms / 1000.0
        self._timer: threading.Timer | None = None

    def __enter__(self) -> "_SqliteWatchdog":
        self._timer = threading.Timer(self._timeout, self._conn.interrupt)
        self._timer.daemon = True
        self._timer.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None


class DatasetAdapter:
    """Discovery adapter over the local FTS5 community recipe corpus.

    NOTE: This adapter does not extend SiteAdapter because it is not bound
    to a per-row DiscoverySite — it is a singleton over the on-disk dataset
    DB. It is still registered in the discovery registry and exposes the
    same `search(query, limit) -> list[RecipeStub]` contract.
    """

    kind = "dataset"

    # Q4.3: published so introspection tests can verify schema coverage.
    SANITIZED_FIELDS: tuple[str, ...] = (
        "title",
        "description",
        "ingredients",
        "instructions",
        "tags",
        "source_name",
    )

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def is_available(self) -> bool:
        return self._db_path.exists()

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = open_readonly(self._db_path)
        return self._conn

    async def search(self, query: str, limit: int = 20) -> list[RecipeStub]:
        """Search the dataset corpus.

        Returns [] on any FTS5 parse error or query timeout (Q2.4).
        Never raises to the caller.
        """
        if not self.is_available():
            return []

        match_expr = _build_match_expression(query or "")
        limit = max(1, min(int(limit or 20), 50))

        try:
            conn = self._connection()
            with _SqliteWatchdog(conn, QUERY_TIMEOUT_MS):
                rows = conn.execute(
                    """
                    SELECT r.row_id, r.title, r.description, r.source_url, r.image_url
                    FROM recipes r
                    JOIN recipes_fts f ON f.rowid = r.row_id
                    WHERE recipes_fts MATCH ?
                    ORDER BY bm25(recipes_fts)
                    LIMIT ?
                    """,
                    (match_expr, limit),
                ).fetchall()
        except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
            # Q2.4: never propagate FTS parse exceptions as 5xx.
            log.warning(
                "dataset_adapter: query failed",
                exc_class=exc.__class__.__name__,
                # NOTE: do NOT include the raw user query in the log per Q2.4.
            )
            return []

        return [self._row_to_stub(row) for row in rows]

    def _row_to_stub(self, row: sqlite3.Row) -> RecipeStub:
        row_id = int(row["row_id"])
        title = (row["title"] or "").strip() or "(untitled)"
        description = row["description"]
        if description:
            description = description[:280]

        # `internal://dataset/<row_id>` per Q3.2; row_id is already an INTEGER
        # PRIMARY KEY in the DB and we cap at SQLITE_INT_MAX at import time.
        source_url = row["source_url"]
        validated = _validate_public_url(source_url) if source_url else None
        if validated is None:
            url = f"internal://dataset/{row_id}"
            # Defense-in-depth: re-validate the synthesized URL with the same
            # parser used at the resolver boundary (Q3.4).
            parse_internal_dataset_url(url)
        else:
            url = validated

        image_url = _validate_public_url(row["image_url"]) if row["image_url"] else None

        return RecipeStub(
            id="stub_" + str(uuid.uuid4()),
            title=title,
            url=url,
            source_site=SourceSite(slug="dataset", name="Community Dataset"),
            thumbnail_url=image_url,
            description=description,
            origin="search",
        )
