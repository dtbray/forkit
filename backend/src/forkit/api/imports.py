"""Read-only progress for operator-configured category import workers."""

import json
from pathlib import Path

from fastapi import APIRouter

from ..config import get_settings

router = APIRouter()


@router.get("/imports")
def import_status() -> dict:
    root = Path(get_settings().forkit_cache_dir).parent / "imports"
    sources = []
    for path in sorted(root.glob("*/status.json")):
        try:
            sources.append(json.loads(path.read_text()))
        except (OSError, ValueError):
            continue
    return {"sources": sources}
