# Hexagonal Architecture Notes

## Goal
Clarify the current boundaries and identify places where app services depend on adapters directly.

## Intended boundaries
- Domain / application: `gateway/app/services`, `gateway/app/steps`, `gateway/app/core`
- Ports: `gateway/app/ports` and `gateway/ports`
- Adapters: `gateway/app/adapters`, `gateway/adapters`
- Delivery: `gateway/app/routers`, `gateway/routes`, `gateway/main.py`, `gateway/app/main.py`

## Current boundary issues
- `gateway/app/config.py` instantiates adapter classes (`gateway/app/adapters/storage_r2.py`, `gateway/app/adapters/storage_local.py`) directly.
  - Services and steps call `get_storage_service()` from config, which couples application code to adapters via global configuration.
- `gateway/app/services/artifact_storage.py` relies on `get_storage_service()` (adapter wiring) instead of a port injected at the boundary.
- `gateway/app/deps.py` provides a port-oriented API but is a stub for storage, so delivery code bypasses it.

## Impacts
- Harder to swap storage backends in tests without monkeypatching globals.
- Duplicated routing layers choose different entrypoints and config paths.
- Mixed repository types (DB vs file) complicate port contracts.

## Minimal doc-only remediation plan
1) Declare a single storage port interface as the required dependency for pack download/upload.
2) Document adapter wiring in one place (prefer DI in entrypoint).
3) Update code comments to reflect the preferred entrypoint (`gateway/main.py`) and legacy status of `gateway/app/main.py`.
