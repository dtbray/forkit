"""Forkit CLI entry point.

Exposes a small `argparse`-based command surface so we don't pull in `click`
as a new dependency. Currently provides:

    forkit dataset import foodcom --data-path <path> --accept-license
    forkit dataset stats

Both commands operate on a dataset DB located at:
    <FORKIT_CACHE_DIR or /data/cache>/forkit_dataset.db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import get_settings
from .dataset.db import get_meta, open_readonly
from .dataset.importer import (
    LICENSE_NOTICE_TEXT,
    LicenseNotAcceptedError,
    import_foodcom,
)


def _dataset_db_path() -> Path:
    """Default dataset DB path: <cache_dir>/forkit_dataset.db."""
    settings = get_settings()
    cache_dir = Path(settings.forkit_cache_dir)
    return cache_dir / "forkit_dataset.db"


def _cmd_dataset_import(args: argparse.Namespace) -> int:
    if args.source != "foodcom":
        print(f"unknown dataset source: {args.source!r}", file=sys.stderr)
        return 2

    print(LICENSE_NOTICE_TEXT, file=sys.stderr)
    print("", file=sys.stderr)

    if not args.accept_license:
        print(
            "Refusing to import without --accept-license. "
            "Re-run with --accept-license after reading the notice above.",
            file=sys.stderr,
        )
        return 2

    data_path = Path(args.data_path).expanduser().resolve()
    db_path = Path(args.db_path).expanduser().resolve() if args.db_path else _dataset_db_path()

    try:
        result = import_foodcom(
            data_path=data_path,
            db_path=db_path,
            accept_license=True,
        )
    except LicenseNotAcceptedError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(
        f"Imported {result['row_count']} recipes "
        f"({result.get('skipped', 0)} skipped) into {db_path}",
        file=sys.stderr,
    )
    return 0


def _cmd_dataset_stats(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path).expanduser().resolve() if args.db_path else _dataset_db_path()
    if not db_path.exists():
        print(f"no dataset DB at {db_path}", file=sys.stderr)
        return 1
    conn = open_readonly(db_path)
    try:
        keys = [
            "source_name",
            "source_license",
            "source_url",
            "source_attribution",
            "imported_at",
            "record_count",
            "bleach_version",
            "sanitizer_config_hash",
            "schema_version",
        ]
        for k in keys:
            v = get_meta(conn, k)
            print(f"{k}: {v}")
    finally:
        conn.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forkit")
    sub = parser.add_subparsers(dest="group", required=True)

    dataset = sub.add_parser("dataset", help="Manage the community recipe dataset")
    dataset_sub = dataset.add_subparsers(dest="action", required=True)

    imp = dataset_sub.add_parser("import", help="Import a dataset into the FTS5 DB")
    imp.add_argument("source", choices=["foodcom"])
    imp.add_argument(
        "--data-path",
        required=True,
        help="Path to RAW_recipes.csv (Food.com Kaggle download)",
    )
    imp.add_argument(
        "--db-path",
        default=None,
        help="Override dataset DB output path (default: <cache_dir>/forkit_dataset.db)",
    )
    imp.add_argument(
        "--accept-license",
        action="store_true",
        help="Required to acknowledge CC-BY-SA 3.0 + Kaggle terms (Security Q1.1)",
    )
    imp.set_defaults(func=_cmd_dataset_import)

    stats = dataset_sub.add_parser("stats", help="Show dataset_meta from the imported DB")
    stats.add_argument("--db-path", default=None)
    stats.set_defaults(func=_cmd_dataset_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
