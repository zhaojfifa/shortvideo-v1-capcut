# v1.8 Ops Handoff (Release/v1.8)

This document is the operational handoff contract for the v1.8 stable ops flow.
It is written to prevent ?route cross-over? and to keep /tasks + /api/tasks stable.

## 1. Two Lines Model (Do Not Drift)

### 1) Ops/Task line (authoritative for v1.8 ops)
UI:
- /tasks
- /tasks/new
- /tasks/{task_id}  (workbench)

API:
- /api/tasks/*
  - /api/tasks
  - /api/tasks/{id}
  - /api/tasks/{id}/subtitles
  - /api/tasks/{id}/dub
  - /api/tasks/{id}/scenes

Downloads (302 redirect to R2):
- /v1/tasks/{id}/pack
- /v1/tasks/{id}/scenes
- /v1/tasks/{id}/raw
- /v1/tasks/{id}/audio_mm
- /v1/tasks/{id}/subs_mm
- /v1/tasks/{id}/subs_origin
- /v1/tasks/{id}/mm_txt

### 2) Legacy debug line (v1 pipeline lab)
UI:
- /ui

API (legacy only):
- /v1/parse
- /v1/subtitles
- /v1/dub
- /v1/pack

## 2. Non-Interference Rules (Strict)

- /ui MUST NEVER call /api/tasks
  - No creation
  - No polling
  - No status queries

- /tasks + workbench MUST NEVER call /v1/parse|/v1/subtitles|/v1/dub|/v1/pack directly
  - They trigger work via /api/tasks/...
  - They download via /v1/tasks/... (302 only)

## 3. Polling Discipline (Strict)

- /tasks list polling must be single-instance (no duplicated timers).
- Polling interval must be bounded (no high-frequency spam).
- Prefer conditional polling:
  - poll only when there are queued/processing tasks
  - stop polling when all tasks are done/idle

## 4. v1.8 Storage and Artifacts (Ops View)

### pack.zip (frozen structure)
pack.zip remains the frozen ops baseline structure and must not be made heavier.

### scenes.zip (lightweight)
scenes.zip is separate and must NOT duplicate full assets already in pack.zip.
It should contain only:
- scenes/scene_*/ assets (video/audio/subs/scene.json)
- scenes_manifest.json (machine-read)
- README.md (human-read)

R2 key recommendation:
- deliver/scenes/{task_id}/scenes.zip

## 5. Endpoint Cheat Sheet

### Ops UI
- GET /tasks
- GET /tasks/new
- GET /tasks/{task_id}

### Ops API
- POST/GET /api/tasks
- GET /api/tasks/{id}
- POST /api/tasks/{id}/subtitles
- POST /api/tasks/{id}/dub
- POST /api/tasks/{id}/scenes

### Ops Downloads (302 redirect)
- GET /v1/tasks/{id}/pack
- GET /v1/tasks/{id}/scenes
- GET /v1/tasks/{id}/raw
- GET /v1/tasks/{id}/audio_mm
- GET /v1/tasks/{id}/subs_mm
- GET /v1/tasks/{id}/subs_origin
- GET /v1/tasks/{id}/mm_txt

### Legacy (isolated)
- GET /ui
- POST /v1/parse
- POST /v1/subtitles
- POST /v1/dub
- POST /v1/pack

## 6. Render Manual Verification Checklist

### A) Ops line verification
1) Open /tasks
   - Loads successfully
   - Polling is controlled (no spam in Network tab)
2) Open /tasks/{task_id}
   - Scenes step works (if enabled)
   - Dub step works
   - Downloads work and are 302 redirects:
     - /v1/tasks/{id}/scenes  -> 302 -> R2 presigned
     - /v1/tasks/{id}/pack    -> 302 -> R2 presigned

### B) Legacy line verification (non-interference)
1) Open /ui
2) Confirm /ui calls ONLY /v1/* endpoints
3) Confirm /ui does NOT call /api/tasks anywhere
