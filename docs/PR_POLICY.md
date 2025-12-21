# PR Policy (Phase0 → v1.7/v1.8)

## 1. Purpose
This repository follows strict submission boundaries to prevent accidental UI/template regressions while iterating on backend and pipeline capabilities.
Phase0 focuses on v1.62 hardening and closure; v1.7/v1.8 will extend the system while inheriting the same boundaries.

## 2. Directory Semantics
- gateway/ : API layer, domain logic, ports/adapters, task state and persistence
- pipeline/ : pipeline steps and orchestration (runner/step), produces artifacts and references
- docs/ : architecture constraints, PR rules, verification checklists, runbooks
- static/ : web UI (Workbench/TaskBoard), client-side interactions
- static/templates/ : template injection / rendering templates (FROZEN by default)

## 3. Hard Boundary Rules
### Allowed / Forbidden Paths by PR Type
1) docs-only PR
- Allowed: docs/**
- Forbidden: everything else

2) backend-only PR
- Allowed: gateway/**, pipeline/**, docs/**
- Forbidden: static/**, static/templates/**

3) ui-only PR (no templates)
- Allowed: static/** except static/templates/**
- Allowed: docs/** (optional)
- Forbidden: static/templates/**, gateway/**, pipeline/**

4) template-change PR (special)
- Allowed: static/templates/** (and only the minimum needed)
- Allowed: docs/** (must update screenshots/regression notes)
- Forbidden: unrelated static/** changes unless strictly required

### Absolute Freeze Gate
- static/templates/** must not change unless the PR is explicitly labeled and reviewed as "template-change".

## 4. PR Labels and Required Checks
### docs-only
- Diff scope: docs/** only
- Checks: markdown lint (if exists), reviewer confirms rules are clear and operational

### backend-only
- Diff scope: gateway/** and/or pipeline/**
- Checks:
  - API smoke via Render deploy: create task → run pipeline steps → list/get task
  - Persistence check: restart and verify task data still exists
  - Storage namespace: all artifacts under {tenant}/{category}/{task_id}/...

### ui-only (no templates)
- Diff scope: static/** excluding static/templates/**
- Checks:
  - Web verification: Workbench shows expected fields; Task Board renders; no console errors
  - Template freeze: confirm static/templates/** untouched

### template-change (special)
- Diff scope: static/templates/** only (minimum changes)
- Checks:
  - Mandatory screenshots: before/after key pages
  - Regression checklist R0/R1/R2 must be re-run
  - Additional reviewer approval required

## 5. STOP Conditions (Do Not Merge)
- Any PR modifies static/templates/** without "template-change" classification and explicit review.
- Any PR mixes backend changes with template injection changes.
- Any PR fails the global regression steps (R0/R1/R2) after Render deploy.
- Any PR introduces direct path-building in business/UI layers instead of using storage service output URLs.
