# v1.8 P0 Acceptance Criteria

## UI -> API routing matrix
- Task Workbench (`/tasks/{id}`): trigger via `POST /api/tasks/{task_id}/parse|subtitles|dub|pack|scenes`; download via `GET /v1/tasks/{task_id}/...` (302 to presigned).
- Pipeline Lab (`/ui`): trigger via `POST /api/tasks/{task_id}/parse|subtitles|dub|pack`; download via `GET /v1/tasks/{task_id}/...`.

## Manual verification (Render)
- Task Workbench: parse/subtitles/dub/pack/scenes buttons call `POST /api/tasks/{task_id}/...` (Network tab).
- Pipeline Lab: parse/subtitles/dub/pack buttons call `POST /api/tasks/{task_id}/...` (Network tab).
- Subtitles: `POST /api/tasks/{task_id}/subtitles` must succeed without 500; `origin.srt` + `subtitles.json` exist.
- Dub: `POST /api/tasks/{task_id}/dub` returns 400 when subtitles are missing.
- Pack: `POST /api/tasks/{task_id}/pack` completes and `/v1/tasks/{task_id}/pack` returns 302.
- Scenes trigger: `POST /api/tasks/{task_id}/scenes` returns `queued|already_ready`; `scenes_status` updates to `ready`.
- Scenes download: `GET /v1/tasks/{task_id}/scenes` returns 302 to presigned URL.
- ZIP layout: `deliver/scenes/{task_id}/README.md`, `scenes_manifest.json`, and `scenes/scene_001/{video.mp4,audio.wav,subs.srt,scene.json}`.
- v1.7: `/v1.7/pack/youcut` unchanged and still works.

## Contract
- Task Workbench triggers only `/api/tasks/{task_id}/...` (no `/v1` triggers).
- Pipeline Lab triggers only `/api/tasks/{task_id}/...` (no `/v1` triggers).
- Downloads only via `/v1/tasks/{task_id}/...` (302 to presigned URL).
- Scenes input only from `deliver/subtitles/{task_id}/...` (no pack fallback).
- Gemini failures never stop subtitles; fallback to whisper-only timestamps.
