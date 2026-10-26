"""Run declaratively configured, resumable category jobs in fair batches."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit

from .wordpress import CategoryImporter, ImportPaused, source_location


def source_origin(url: str) -> tuple[str, str | None, int | None]:
    parts = urlsplit(url)
    return parts.scheme, parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)


def load_config(path: Path) -> dict:
    config = json.loads(path.read_text())
    sources = config.get("sources")
    if not isinstance(sources, list) or not sources or not all(isinstance(x, str) for x in sources):
        raise ValueError("sources must be a nonempty list of category URLs")
    sources = list(dict.fromkeys(source_location(url)[0] for url in sources))
    delay = float(config.get("delay_seconds", 5))
    batch = int(config.get("batch_size", 10))
    interval = int(config.get("refresh_seconds", 86400))
    if not 2 <= delay <= 3600 or not 1 <= batch <= 100 or interval < 300:
        raise ValueError("delay_seconds must be 2..3600, batch_size 1..100, refresh_seconds >= 300")
    return {"sources": sources, "delay": delay, "batch": batch, "interval": interval}


async def run_worker(config: dict, *, once: bool = False) -> None:
    importers = [CategoryImporter(url, delay=config["delay"]) for url in config["sources"]]
    refresh = False
    last_request = 0.0
    try:
        while True:
            active = list(importers)
            paused_origins = set()
            first_pass = True
            while active:
                next_round = []
                for importer in active:
                    if source_origin(importer.url) in paused_origins:
                        continue
                    # One sequential worker, shared pacing across sources on the same host.
                    importer.last_request = last_request
                    try:
                        result = await importer.run(
                            refresh=refresh and first_pass,
                            limit=config["batch"],
                            retry_failed=first_pass,
                        )
                        print(json.dumps(result), flush=True)
                        if importer.has_pending_work():
                            next_round.append(importer)
                    except Exception as exc:
                        if isinstance(exc, ImportPaused):
                            origin = source_origin(importer.url)
                            paused_origins.add(origin)
                            for peer in importers:
                                if peer is not importer and source_origin(peer.url) == origin:
                                    peer.stage = "paused"
                                    peer.error = f"Publisher paused another category: {exc}"[:500]
                                    peer.publish()
                        print(
                            json.dumps(
                                {"source_url": importer.url, "error": str(exc), "stage": "paused"}
                            ),
                            flush=True,
                        )
                    finally:
                        last_request = max(last_request, importer.last_request)
                active = [job for job in next_round if source_origin(job.url) not in paused_origins]
                first_pass = False
            if once:
                return
            await asyncio.sleep(config["interval"])
            refresh = True
    finally:
        for importer in importers:
            importer.db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", action="store_true", help="Drain current manifests and exit")
    args = parser.parse_args()
    asyncio.run(run_worker(load_config(args.config), once=args.once))


if __name__ == "__main__":
    main()
