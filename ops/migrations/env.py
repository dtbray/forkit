import sys
import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, engine_from_config, event, pool

from alembic import context

# ---------------------------------------------------------------------------
# Make the backend package importable when alembic runs from the project root.
# ---------------------------------------------------------------------------
_backend_src = str(Path(__file__).resolve().parents[2] / "backend" / "src")
if _backend_src not in sys.path:
    sys.path.insert(0, _backend_src)

from forkit.config import get_settings  # noqa: E402
from forkit.models import Base  # noqa: E402  (imports all models, populates metadata)

# ---------------------------------------------------------------------------
# Alembic config object.
# ---------------------------------------------------------------------------
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db_url() -> str:
    """Resolve the database URL.

    Priority order:
    1. ``sqlalchemy.url`` set explicitly in the Alembic Config object
       (used by tests to pass an in-memory URI without touching env vars).
    2. ``FORKIT_DB_PATH`` environment variable.
    3. Default from pydantic-settings (``/data/forkit.db``).
    """
    # If the caller set it programmatically (e.g. conftest.py), honour it.
    cfg_url = config.get_main_option("sqlalchemy.url", default="")
    if cfg_url:
        return cfg_url
    db_path = os.environ.get("FORKIT_DB_PATH", get_settings().forkit_db_path)
    return f"sqlite:///{db_path}"


def _apply_sqlite_pragmas(dbapi_conn: object, _: object) -> None:
    cursor = dbapi_conn.cursor()  # type: ignore[union-attr]
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


# ---------------------------------------------------------------------------
# Offline mode
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL emitted to stdout/file)."""
    url = _db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode
# ---------------------------------------------------------------------------

def run_migrations_online() -> None:
    """Run migrations in 'online' mode (directly against the DB)."""
    connectable = create_engine(
        _db_url(),
        connect_args={"check_same_thread": False},
        poolclass=pool.NullPool,
    )

    event.listen(connectable, "connect", _apply_sqlite_pragmas)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # required for SQLite ALTER TABLE support
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
