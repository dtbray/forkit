# ops/compose

HermitHost-aware docker-compose overrides for forkit.

Convention: single `web` service, `forkit-data:/data` volume, Traefik ingress at `forkit.hh` (LAN-only). See ADR-001 §3f.
