# Phase0 Acceptance Checklist (v1.62 closure hardening)

## 0. Phase0 PR Plan (PR split)
- PR-0: docs-only — PR policy + Phase0 checklist
- PR-1: ports skeleton — introduce interfaces and DI shell, no behavior changes
- PR-2: TaskRepository — unify all task persistence through repository
- PR-3: publish backfill — API + persistence of published_url/published_at/...
- PR-4: storage service — S3/R2 adapter + namespace isolation + unified download URL
- PR-5: UI hardening — Workbench backfill UI + Board published badge, templates frozen

## 1. Module Acceptance (Must Pass)

### A) gateway: API + publish backfill persistence
- [ ] Publish backfill API writes to TaskRepository (published_url at minimum)
- [ ] GET /api/tasks/{id} returns published fields after backfill
- [ ] Restart service and confirm published fields persist
- [ ] Non-existent task_id returns 404 (no ghost record)

### B) gateway: TaskRepository constraints
- [ ] No business code directly reads/writes tasks.json or global dict (repo-only)
- [ ] Repository supports create/get/list/update
- [ ] Minimal concurrency safety (no overwrite between two quick creates)

### C) gateway + pipeline: Storage namespace isolation
- [ ] All artifact keys follow: {tenant}/{category}/{task_id}/...
- [ ] Download URLs returned to UI are produced by storage service (no manual URL/path concatenation)
- [ ] Two parallel tasks do not overwrite each other’s raw/subs/audio/pack

### D) static: Web UI verification (templates frozen)
- [ ] Workbench: backfill input + save + reload persists
- [ ] Task Board: Published badge visible and consistent with task data
- [ ] No console errors in web verification on Render deployment
- [ ] No changes under static/templates/**

### E) templates: Freeze gate
- [ ] static/templates/** remains unchanged across PR-0..PR-5
- [ ] If templates must change, create a dedicated "template-change" PR with screenshots + full regression

## 2. Global Regression (after Render deploy; web verification)

### R0: Closed-loop persistence
1) Create Task A (URL1) → run to pack (or farthest step)
2) Create Task B (URL2) → run same
3) Backfill published_url for Task A
4) Refresh: Task A shows Published
5) Restart / redeploy: Task A still shows Published

### R1: Namespace isolation
- Verify Task A artifacts are under A’s prefix; Task B artifacts are under B’s prefix
- Randomly download A links: should never fetch B artifacts

### R2: Template freeze verification
- Confirm git diff across Phase0 PRs shows no changes under static/templates/**
