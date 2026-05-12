"""Dataset import pipeline — ADR-003.

CLI entry point: `forkit dataset import foodcom --data-path <csv> --accept-license`

Security conditions enforced:
  Q1.1 — `--accept-license` required or LicenseNotAcceptedError raised.
  Q1.2 — dataset_meta records source_name, source_license, source_url,
         source_attribution, imported_at, kaggle_terms_acknowledged_at,
         bleach_version, sanitizer_config_hash.
  Q1.4 — atomic write: forkit_dataset.db.new -> rename to forkit_dataset.db.
  Q4.1 — bleach.clean(tags=[], attributes={}, protocols=[], strip=True,
         strip_comments=True) applied to every column in SANITIZED_FIELDS.
  Q4.4 — bleach_version + sanitizer_config_hash recorded in dataset_meta.
  Q4.5 — URL fields restricted to http/https; numeric fields coerced/bounded.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import bleach
import structlog

from .db import (
    SANITIZED_FIELDS,
    SCHEMA_VERSION,
    init_schema,
    open_writable,
    set_meta,
)

log = structlog.get_logger()


class LicenseNotAcceptedError(RuntimeError):
    """Raised when the importer is invoked without --accept-license."""


# ---------------------------------------------------------------------------
# License / attribution constants — Q1.1, Q1.2
# ---------------------------------------------------------------------------

FOODCOM_SOURCE_NAME = "foodcom"
FOODCOM_SOURCE_URL = (
    "https://www.kaggle.com/datasets/shuyangli94/food-com-recipes-and-user-interactions"
)
FOODCOM_LICENSE = "CC-BY-SA-3.0"
FOODCOM_ATTRIBUTION = (
    "Food.com Recipes and User Interactions dataset, sourced from Kaggle, "
    "licensed CC-BY-SA 3.0. Imported data inherits this license. "
    f"Source: {FOODCOM_SOURCE_URL}"
)
LICENSE_NOTICE_TEXT = (
    f"{FOODCOM_ATTRIBUTION}\n\n"
    "By proceeding you accept these terms."
)


# ---------------------------------------------------------------------------
# Bleach configuration — Q4.1
# ---------------------------------------------------------------------------

BLEACH_CONFIG = {
    "tags": [],
    "attributes": {},
    "protocols": [],
    "strip": True,
    "strip_comments": True,
}


def _bleach_clean(text: str | None) -> str | None:
    """Apply the policy-mandated bleach.clean call. Q4.1."""
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    cleaned = bleach.clean(
        s,
        tags=BLEACH_CONFIG["tags"],
        attributes=BLEACH_CONFIG["attributes"],
        protocols=BLEACH_CONFIG["protocols"],
        strip=BLEACH_CONFIG["strip"],
        strip_comments=BLEACH_CONFIG["strip_comments"],
    ).strip()
    return cleaned or None


def sanitizer_config_hash() -> str:
    """SHA-256 of the JSON-serialized bleach config — Q4.4."""
    payload = json.dumps(BLEACH_CONFIG, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Field validators — Q4.5
# ---------------------------------------------------------------------------

_PUBLIC_URL_SCHEMES = {"http", "https"}
_ALL_URL_SCHEMES = {"http", "https", "internal"}


def _validate_url(url: str | None, *, allow_internal: bool = False) -> str | None:
    """Return URL if scheme is allowed; else None."""
    if not url:
        return None
    s = str(url).strip()
    if not s:
        return None
    parsed = urlparse(s)
    allowed = _ALL_URL_SCHEMES if allow_internal else _PUBLIC_URL_SCHEMES
    if parsed.scheme not in allowed:
        return None
    if parsed.scheme in _PUBLIC_URL_SCHEMES and not parsed.netloc:
        return None
    return s


def _coerce_int(value: object, *, lo: int, hi: int) -> int | None:
    """Coerce to int and enforce bounds; else None."""
    if value is None or value == "":
        return None
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return None
    if n < lo or n > hi:
        return None
    return n


# ---------------------------------------------------------------------------
# Row processing
# ---------------------------------------------------------------------------


@dataclass
class _RecipeRow:
    source_name: str
    source_url: str | None
    title: str
    description: str | None
    ingredients: str | None
    instructions: str | None
    tags: str | None
    minutes: int | None
    servings: int | None
    image_url: str | None


def _normalize_list_field(raw: str | None) -> str | None:
    """Food.com CSV list-shaped fields (`['a','b']`) -> newline-separated text.

    Falls back to passing the raw string through bleach if it isn't a JSON list.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.startswith("[") and s.endswith("]"):
        # Replace single quotes with double for a best-effort JSON parse.
        try:
            items = json.loads(s.replace("'", '"'))
            if isinstance(items, list):
                return "\n".join(str(item).strip() for item in items if str(item).strip())
        except (json.JSONDecodeError, ValueError):
            pass
    return s


def _process_row(raw: dict) -> _RecipeRow | None:
    """Map a Food.com CSV row to a sanitized _RecipeRow, or None to skip.

    Skips rows with missing title or ingredients (per ADR-003 §3 step 4).
    """
    title = _bleach_clean(raw.get("name") or raw.get("title"))
    if not title:
        return None

    ingredients_raw = raw.get("ingredients")
    instructions_raw = raw.get("steps") or raw.get("instructions")
    tags_raw = raw.get("tags")

    ingredients = _bleach_clean(_normalize_list_field(ingredients_raw))
    if not ingredients:
        return None

    instructions = _bleach_clean(_normalize_list_field(instructions_raw))
    tags = _bleach_clean(_normalize_list_field(tags_raw))
    description = _bleach_clean(raw.get("description"))

    minutes = _coerce_int(raw.get("minutes"), lo=0, hi=100_000)
    servings = _coerce_int(raw.get("servings") or raw.get("n_servings"), lo=0, hi=10_000)

    # Food.com rows generally lack a source_url; we synthesize internal:// at
    # query time per ADR-003 §4. If the CSV does carry one, validate it.
    source_url = _validate_url(raw.get("source_url"))
    image_url = _validate_url(raw.get("image_url"))

    return _RecipeRow(
        source_name=FOODCOM_SOURCE_NAME,
        source_url=source_url,
        title=title,
        description=description,
        ingredients=ingredients,
        instructions=instructions,
        tags=tags,
        minutes=minutes,
        servings=servings,
        image_url=image_url,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def import_foodcom(
    data_path: Path,
    *,
    db_path: Path,
    accept_license: bool = False,
    batch_size: int = 5000,
) -> dict:
    """Import a Food.com RAW_recipes.csv into a fresh forkit_dataset.db.

    Atomically replaces `db_path` on success (Q1.4).

    Returns a summary dict: {row_count, source_name, source_license, imported_at}.

    Raises:
      LicenseNotAcceptedError — if `accept_license` is not True.
      FileNotFoundError — if `data_path` does not exist.
    """
    if not accept_license:
        raise LicenseNotAcceptedError(
            "Importing the Food.com dataset requires acceptance of CC-BY-SA 3.0. "
            "Re-run with --accept-license after reading the notice."
        )

    data_path = Path(data_path)
    if not data_path.exists():
        raise FileNotFoundError(f"dataset CSV not found: {data_path}")

    db_path = Path(db_path)
    tmp_path = db_path.with_suffix(db_path.suffix + ".new")
    if tmp_path.exists():
        tmp_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = open_writable(tmp_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        init_schema(conn)

        row_count = 0
        skipped = 0
        next_row_id = 1
        buffer: list[_RecipeRow] = []

        with data_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for raw in reader:
                processed = _process_row(raw)
                if processed is None:
                    skipped += 1
                    continue
                buffer.append(processed)
                if len(buffer) >= batch_size:
                    next_row_id = _flush_batch(conn, buffer, next_row_id)
                    row_count += len(buffer)
                    buffer.clear()
            if buffer:
                next_row_id = _flush_batch(conn, buffer, next_row_id)
                row_count += len(buffer)
                buffer.clear()

        now = datetime.now(timezone.utc).isoformat()
        set_meta(conn, "schema_version", SCHEMA_VERSION)
        set_meta(conn, "source_name", FOODCOM_SOURCE_NAME)
        set_meta(conn, "source_license", FOODCOM_LICENSE)
        set_meta(conn, "source_url", FOODCOM_SOURCE_URL)
        set_meta(conn, "source_attribution", FOODCOM_ATTRIBUTION)
        set_meta(conn, "imported_at", now)
        set_meta(conn, "kaggle_terms_acknowledged_at", now)
        set_meta(conn, "record_count", str(row_count))
        set_meta(conn, "bleach_version", bleach.__version__)
        set_meta(conn, "sanitizer_config_hash", sanitizer_config_hash())

        conn.execute("ANALYZE")
        conn.commit()
    finally:
        conn.close()

    # Q1.4: atomic swap.
    os.replace(tmp_path, db_path)

    log.info(
        "dataset import complete",
        row_count=row_count,
        skipped=skipped,
        db_path=str(db_path),
    )

    return {
        "row_count": row_count,
        "skipped": skipped,
        "source_name": FOODCOM_SOURCE_NAME,
        "source_license": FOODCOM_LICENSE,
        "imported_at": now,
    }


def _flush_batch(conn, batch: list[_RecipeRow], next_row_id: int) -> int:
    """Bulk-insert a batch with explicit row_ids; return the next available row_id."""
    rows = [
        (
            next_row_id + i,
            r.source_name,
            r.source_url,
            r.title,
            r.description,
            r.ingredients,
            r.instructions,
            r.tags,
            r.minutes,
            r.servings,
            r.image_url,
        )
        for i, r in enumerate(batch)
    ]
    with conn:
        conn.executemany(
            """
            INSERT INTO recipes (
                row_id, source_name, source_url, title, description,
                ingredients, instructions, tags, minutes, servings, image_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return next_row_id + len(batch)
