"""FTS5 schema and connection helpers for the dataset corpus — ADR-003.

The dataset lives in a **separate** SQLite DB file from the main app DB:
  - read path: opens via URI `?mode=ro&immutable=1` (per Security Condition Q3.5).
  - write path: opens normally; only the importer ever writes.

Schema is defined here in one place so the importer, the adapter, and the
SANITIZED_FIELDS introspection test all agree on column shape.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# ---------------------------------------------------------------------------
# Sanitization policy — Security Condition Q4.3
# ---------------------------------------------------------------------------
# Every TEXT column in `recipes` MUST be in either SANITIZED_FIELDS or
# EXEMPT_FIELDS. The matching test in test_dataset_adapter.py introspects the
# schema and fails CI if a new TEXT column is not categorized.
SANITIZED_FIELDS: tuple[str, ...] = (
    "title",
    "description",
    "ingredients",
    "instructions",
    "tags",
    "source_name",  # constant 'foodcom' at write time but treated as text-bearing
)

EXEMPT_FIELDS: tuple[str, ...] = (
    "source_url",  # validated as http/https/internal scheme instead
    "image_url",  # validated as http/https scheme instead
)

# Columns in `recipes` that are TEXT in SQL terms. Schema introspection
# uses sqlite_master / PRAGMA table_info to derive the actual list at test time;
# this constant is the authoritative expected list.
ALL_TEXT_COLUMNS: tuple[str, ...] = SANITIZED_FIELDS + EXEMPT_FIELDS

SCHEMA_VERSION = "1"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS dataset_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recipes (
    row_id        INTEGER PRIMARY KEY,
    source_name   TEXT NOT NULL,
    source_url    TEXT,
    title         TEXT NOT NULL,
    description   TEXT,
    ingredients   TEXT,
    instructions  TEXT,
    tags          TEXT,
    minutes       INTEGER,
    servings      INTEGER,
    image_url     TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS recipes_fts USING fts5(
    title,
    description,
    ingredients,
    tags,
    content='recipes',
    content_rowid='row_id',
    tokenize = 'porter unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS recipes_ai AFTER INSERT ON recipes BEGIN
    INSERT INTO recipes_fts(rowid, title, description, ingredients, tags)
    VALUES (new.row_id, new.title, new.description, new.ingredients, new.tags);
END;
"""


def open_readonly(db_path: Path) -> sqlite3.Connection:
    """Open the dataset DB read-only and immutable.

    Security Condition Q3.5: `?mode=ro&immutable=1` disables locking/WAL and
    is appropriate for a static read-only corpus. The handle CANNOT mutate
    the DB even if a bug attempted to.
    """
    uri = f"file:{db_path.as_posix()}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def open_writable(db_path: Path) -> sqlite3.Connection:
    """Open the dataset DB for writing (importer-only path)."""
    conn = sqlite3.connect(db_path.as_posix(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Apply the dataset schema. Idempotent."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    """Read a dataset_meta value by key."""
    row = conn.execute(
        "SELECT value FROM dataset_meta WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Upsert a dataset_meta key/value pair."""
    conn.execute(
        "INSERT INTO dataset_meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
