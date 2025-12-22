# Phase0 PR Policy

This document codifies the Phase0 PR boundaries and enforcement rules for this repo. **PR-0 is documentation-only**; no runtime code changes are allowed in PR-0.

## Global rules

- **Frozen assets**: `gateway/app/static/ui.html` is frozen and **may only be changed in a dedicated V1-UI PR**.
- **Never modify** in Phase0 PRs unless the PR slice explicitly allows it:
  - `gateway/**`
  - `pipeline/**`
  - `static/**`
  - `templates/**`
  - `requirements.txt`
- If a change is required outside the allowed paths for the selected PR slice, **stop** and open a separate PR under the correct slice.

## PR slices

### PR-0: Policy & Checklist
**Purpose**: Document boundaries and regression checks.

**Allowed paths**:
- `docs/**`
- `.github/workflows/**` (optional)

**Forbidden paths**:
- Everything else, especially `gateway/**`, `pipeline/**`, `static/**`, `templates/**`, and `requirements.txt`.

---

### PR-1: Task Repository (File/S3/R2)
**Purpose**: Persistence for `/api/tasks` and repository wiring.

**Allowed paths**:
- `gateway/app/routers/tasks.py`
- `gateway/app/deps.py`
- `gateway/ports/task_repository.py`
- `gateway/adapters/task_repository_file.py`
- `gateway/adapters/task_repository_s3.py`
- `gateway/adapters/s3_client.py` (if required)
- `gateway/adapters/r2_s3_client.py` (if required)

**Forbidden paths**:
- All templates/static/docs/publish/admin_publish and any pipeline logic.

---

### PR-2: UI (V1 Pipeline Lab)
**Purpose**: Fix `/ui` page errors or UI-only changes.

**Allowed paths**:
- `gateway/app/static/ui.html`
- UI-specific static assets under `gateway/app/static/` that are strictly required by `/ui`
- UI templates that directly serve `/ui` (if any)

**Forbidden paths**:
- Any `/v1` Python endpoint logic
- `gateway/app/services/**`
- `gateway/app/routers/publish*.py`, `gateway/app/routers/admin_publish*.py`

---

### PR-3: Publish & Archive
**Purpose**: Publish/backfill workflows.

**Allowed paths**:
- `gateway/app/routers/publish*.py`
- `gateway/app/routers/admin_publish*.py`
- `gateway/app/services/publish_service.py`
- `gateway/app/scripts/backfill_publish.py`

**Forbidden paths**:
- `/ui` assets and `/v1` logic

---

### PR-4: Pipeline (Non-V1)
**Purpose**: Pipeline orchestration updates outside `/v1` runtime.

**Allowed paths**:
- `gateway/app/services/**` (excluding `/v1` route handlers)
- `gateway/app/providers/**`

**Forbidden paths**:
- `/v1` routes and UI assets

---

### PR-5: Misc Operations
**Purpose**: Non-functional changes, tooling, or infra.

**Allowed paths**:
- `docs/**`
- `.github/workflows/**`
- repository metadata files (e.g., `.gitignore`)

**Forbidden paths**:
- runtime code under `gateway/**` unless explicitly approved.
