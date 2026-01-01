# Changelog

## 1.8.0

Ops baseline / traceability
- Baseline tag: `v1.8-p0-pack-baseline` (stable pack download redirect + canonical ZIP layout).
- Canonical download endpoint: `GET /v1/tasks/{task_id}/pack` (302 redirect to presigned URL).
- Canonical pack layout: see `docs/v1.8/pack_spec.md`.

Architecture / cleanup
- Converged routing under `gateway/app/routers/*` only; removed duplicate `/v1/tasks/{task_id}/pack` handler risk.
- Wired storage via port/provider (`gateway/app/ports/storage_provider.py`), keeping services off adapters and centralizing composition in entrypoints.
- Removed legacy pack shims and import-time side effects (e.g., mkdir at import).

Tests / regression gates
- Route uniqueness gate: `tests/test_routes_unique.py` (asserts exactly one GET `/v1/tasks/{task_id}/pack` route).
- Windows import stability: `gateway/__init__.py` + `tests/conftest.py`.
- v1.7 compatibility: `/v1.7/pack/youcut` behavior remains intact.
