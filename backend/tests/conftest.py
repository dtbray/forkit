"""Shared pytest fixtures for forkit backend tests."""

from __future__ import annotations

import tempfile
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# Project root: tests/ -> backend/ -> forkit/
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = _PROJECT_ROOT / "ops" / "migrations"


def _apply_pragmas(dbapi_conn: object, _: object) -> None:
    cursor = dbapi_conn.cursor()  # type: ignore[union-attr]
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def _make_alembic_cfg(db_url: str) -> Config:
    """Build an Alembic Config pointing at ops/migrations with the given URL."""
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


@pytest.fixture(scope="function")
def db_engine():
    """Per-test SQLite file engine with all migrations applied.

    Uses a temporary file so each test gets a clean, isolated database.
    The file is deleted after the test completes.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db_url = f"sqlite:///{db_path}"

    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _apply_pragmas)

    alembic_cfg = _make_alembic_cfg(db_url)
    command.upgrade(alembic_cfg, "head")

    yield engine

    engine.dispose()
    try:
        os.unlink(db_path)
        # Also remove WAL/SHM artefacts if they exist.
        for suffix in ("-wal", "-shm"):
            side = db_path + suffix
            if os.path.exists(side):
                os.unlink(side)
    except OSError:
        pass


@pytest.fixture(scope="function")
def db_session(db_engine) -> Session:
    """Provide a SQLAlchemy session bound to the migrated per-test engine."""
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        yield session
