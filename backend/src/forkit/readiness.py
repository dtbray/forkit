"""Bounded readiness checks for the database and persistent storage."""

import shutil
import sqlite3
import tempfile
from pathlib import Path


def check_readiness(db_path: str, image_dir: str) -> dict[str, str]:
    try:
        path = Path(db_path).resolve()
        # mode=rw avoids accidentally creating a healthy-looking empty database.
        with sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=2) as db:
            db.execute("SELECT id FROM recipe LIMIT 1").fetchone()
            if not db.execute("SELECT version_num FROM alembic_version").fetchone():
                raise RuntimeError("missing schema version")
        for directory in (path.parent, Path(image_dir)):
            if shutil.disk_usage(directory).free < 128 * 1024 * 1024:
                raise RuntimeError("low free space")
            with tempfile.TemporaryFile(dir=directory) as probe:
                probe.write(b"ready")
                probe.flush()
        return {"status": "ok"}
    except (OSError, sqlite3.Error, RuntimeError):
        return {"status": "unavailable"}
