"""Image fetch + variant generation pipeline (S3).

Downloads the hero image via the SSRF-safe fetcher, strips EXIF metadata
by re-encoding through Pillow, and saves three WebP variants:
    thumb  (320 x 240)
    medium (800 x 600)
    hero   (1600 x 1200)

The source filename is never trusted; files are stored under
`{image_dir}/{uuid4}/{variant}.webp`.

Returns the relative path to the hero variant, or None on any failure.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import structlog

log = structlog.get_logger()

VARIANTS: dict[str, tuple[int, int]] = {
    "thumb": (320, 240),
    "medium": (800, 600),
    "hero": (1600, 1200),
}

_IMAGE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB for images (larger than page cap)


async def fetch_and_store_image(url: str, image_dir: str) -> str | None:
    """Download, sanitize, and store image variants.

    Args:
        url: Source image URL.  Passed through `safe_fetch`.
        image_dir: Absolute path to the image storage root.

    Returns:
        Relative path to the hero WebP variant (e.g. "{uuid}/hero.webp"),
        or None on any error (missing image is non-fatal for ingest).
    """
    from .fetcher import FetchError, URLForbiddenError, safe_fetch

    try:
        data = await safe_fetch(url, max_bytes=_IMAGE_MAX_BYTES)
    except (URLForbiddenError, FetchError) as exc:
        log.warning("image fetch blocked or failed", url=url, error=str(exc))
        return None
    except Exception as exc:
        log.warning("image fetch unexpected error", url=url, error=str(exc))
        return None

    return store_image_bytes(data, image_dir)


def store_image_bytes(data: bytes, image_dir: str) -> str | None:
    """Sanitize already-fetched image bytes without making another request."""
    from PIL import Image

    url = "cached image bytes"
    try:
        img = Image.open(io.BytesIO(data))
        img.load()  # Force decode — catches corrupt/polyglot files early
    except Exception as exc:
        log.warning("image decode failed — not a valid image", url=url, error=str(exc))
        return None

    # Strip EXIF / metadata by reconstructing a clean image (S3).
    # We copy pixel data into a fresh Image object; Pillow does not carry
    # metadata across this boundary.
    try:
        # Convert to RGB for WebP compatibility (drops transparency alpha for now)
        clean_img = img.convert("RGBA") if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")
        # Re-create from raw pixel data — severs any metadata/EXIF association
        sanitized = Image.frombytes(clean_img.mode, clean_img.size, clean_img.tobytes())
    except Exception as exc:
        log.warning("image sanitization failed", url=url, error=str(exc))
        return None

    img_id = str(uuid.uuid4())
    out_dir = Path(image_dir) / img_id
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.error("cannot create image output directory", path=str(out_dir), error=str(exc))
        return None

    for name, (max_w, max_h) in VARIANTS.items():
        try:
            variant = sanitized.copy()
            variant.thumbnail((max_w, max_h), Image.LANCZOS)
            # WebP with quality=85; no exif kwarg → no metadata written
            variant.save(out_dir / f"{name}.webp", "WEBP", quality=85)
        except Exception as exc:
            log.warning("image variant save failed", variant=name, url=url, error=str(exc))
            # Continue — save what we can

    hero_path = out_dir / "hero.webp"
    if hero_path.exists():
        # Return path relative to image_dir
        return str(Path(img_id) / "hero.webp")

    return None
