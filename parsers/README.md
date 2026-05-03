# parsers

Per-site recipe adapters. Importable from backend via the adapter registry (see ADR-001 §3c).

Each adapter implements:
```python
class Adapter:
    hostname_patterns: list[str]
    def parse(self, html: str, url: str) -> Recipe | None: ...
```

Adapter test fixtures live alongside the adapter (snapshot-based per ADR-001 §3c).
