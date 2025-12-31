# Docs Overview

## Inventory
- Total docs files (pre-update): 22
- Inventory source: `docs/` tree captured during review.

## Current structure
- Core references: `docs/ARCHITECTURE.md`, `docs/REPO_STRUCTURE.md`, `docs/API.md`.
- v1.7 notes: `docs/v1.7_*`.
- New v1.8 notes: `docs/v1.8_pack_p0_changelog.md`.

## Redundancy / overlap
- Two FastAPI entrypoints with overlapping routes:
  - `gateway/main.py` (primary per ARCHITECTURE.md).
  - `gateway/app/main.py` (legacy but active).
- Two router families with similar responsibilities:
  - `gateway/routes/*` vs `gateway/app/routers/*`.
- Duplicate pack download route:
  - `gateway/routes/v1.py` -> `/tasks/{task_id}/pack`
  - `gateway/app/routers/tasks.py` -> `/v1/tasks/{task_id}/pack`
  - `gateway/app/routers/publish.py` -> `/v1/tasks/{task_id}/pack`

## Minimal doc updates plan (no code changes)
1) Document the active entrypoint and route ownership.
2) Define the v1.8 pack spec and ZIP layout (source of truth).
3) Capture operational baseline for v1.8 pack generation and download.
4) Move legacy notes into a dedicated `docs/legacy/` index.
