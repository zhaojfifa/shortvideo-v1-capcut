# Legacy Components Index

This directory documents legacy or duplicate components kept for compatibility.

## Routing / entrypoints
- `gateway/app/main.py` (legacy FastAPI entrypoint; overlaps with `gateway/main.py`).
- `gateway/routes/*` (older router set).
- `gateway/app/routers/*` (newer router set).

## Compatibility shims
- `gateway/app/services/dubbing.py` (legacy import shim).
- `gateway/app/services/pack.py` (legacy import shim).

## Why it exists
- Historical migrations left dual entrypoints and overlapping routers.
- Some deployments still reference legacy paths.

## Plan (doc-only)
- Keep this index updated as components are retired or unified.
