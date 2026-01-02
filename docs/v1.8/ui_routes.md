# v1.8 UI Route Contracts

This document freezes the UI -> API routing matrix for v1.8 to prevent cross-wiring.

## Task Workbench (/tasks/{id})

Triggers (canonical /api):
- Parse: `POST /api/tasks/{task_id}/parse`
- Subtitles: `POST /api/tasks/{task_id}/subtitles`
- Dub: `POST /api/tasks/{task_id}/dub`
- Pack: `POST /api/tasks/{task_id}/pack`
- Scenes: `POST /api/tasks/{task_id}/scenes`

Downloads (302 to presigned):
- Raw: `GET /v1/tasks/{task_id}/raw`
- Subtitles: `GET /v1/tasks/{task_id}/subs_origin`, `GET /v1/tasks/{task_id}/subs_mm`
- Dub audio: `GET /v1/tasks/{task_id}/audio_mm`
- Pack: `GET /v1/tasks/{task_id}/pack`
- Scenes: `GET /v1/tasks/{task_id}/scenes`

## Pipeline Lab (/ui)

Triggers (canonical /api):
- Parse: `POST /api/tasks/{task_id}/parse`
- Subtitles: `POST /api/tasks/{task_id}/subtitles`
- Dub: `POST /api/tasks/{task_id}/dub`
- Pack: `POST /api/tasks/{task_id}/pack`

Downloads (302 to presigned):
- Raw: `GET /v1/tasks/{task_id}/raw`
- Subtitles: `GET /v1/tasks/{task_id}/subs_origin`, `GET /v1/tasks/{task_id}/subs_mm`
- Dub audio: `GET /v1/tasks/{task_id}/audio_mm`
- Pack: `GET /v1/tasks/{task_id}/pack`

## Notes
- /api is canonical for triggers in v1.8.
- /v1 is for downloads and compatibility wrappers only.
- Do not add new trigger endpoints under /v1 without updating tests.
