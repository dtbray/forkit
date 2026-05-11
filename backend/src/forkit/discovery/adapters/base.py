"""SiteAdapter abstract base class — ADR-002 Section 7.1."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

from ...models.discovery_site import DiscoverySite
from ..schemas import RecipeStub


class SiteAdapter(ABC):
    """Abstract base for all discovery adapters.

    Each adapter is responsible for producing valid RecipeStub objects.
    Per-call timeout is enforced in service.py (asyncio.wait_for), not here.
    """

    kind: str  # class-level discriminator: "html_scrape" | "google_cse"

    def __init__(self, site: DiscoverySite) -> None:
        self.site = site
        self.config: dict = json.loads(site.adapter_config_json or "{}")

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> list[RecipeStub]:
        """Search the site for the given query and return up to `limit` stubs."""
        ...

    async def health_check(self) -> bool:
        """Optional health check; default always returns True."""
        return True
