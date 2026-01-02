# v1.8 P0 Acceptance Criteria

<<<<<<< HEAD
## UI -> API routing matrix
- Task Workbench (`/tasks/{id}`): trigger via `POST /api/tasks/{task_id}/parse|subtitles|dub|pack|scenes`; download via `GET /v1/tasks/{task_id}/...` (302 to presigned).
- Pipeline Lab (`/ui`): trigger via `POST /api/tasks/{task_id}/parse|subtitles|dub|pack`; download via `GET /v1/tasks/{task_id}/...`.

## Manual verification (Render)
- Task Workbench: parse/subtitles/dub/pack/scenes buttons call `POST /api/tasks/{task_id}/...` (Network tab).
- Pipeline Lab: parse/subtitles/dub/pack buttons call `POST /api/tasks/{task_id}/...` (Network tab).
- Subtitles: `POST /api/tasks/{task_id}/subtitles` must succeed without 500; `origin.srt` + `subtitles.json` exist.
=======
## Manual verification (Render)
- Task Workbench: clicking Generate subtitles must call `POST /api/tasks/{task_id}/subtitles` (not `/v1/subtitles`).
- Subtitles: run `POST /api/tasks/{task_id}/subtitles`; must succeed without 500; `origin.srt` + `subtitles.json` exist.
>>>>>>> parent of 5c690d0 (Merge branch 'fix/v1.8-pr3.2-route-convergence' into release/v1.8)
- Dub: `POST /api/tasks/{task_id}/dub` returns 400 when subtitles are missing.
- Dub/Scenes: after subtitles ready, both actions succeed.
- Scenes trigger: POST `/api/tasks/{task_id}/scenes` returns `queued|already_ready`; `scenes_status` updates to `ready`.
- Scenes download: GET `/v1/tasks/{task_id}/scenes` returns 302 to presigned URL.
- ZIP layout: `deliver/scenes/{task_id}/README.md`, `scenes_manifest.json`, and `scenes/scene_001/{video.mp4,audio.wav,subs.srt,scene.json}`.
- v1.7: `/v1.7/pack/youcut` unchanged and still works.

## Contract
- Single trigger path: POST `/api/tasks/{task_id}/scenes`.
- Single download path: GET `/v1/tasks/{task_id}/scenes`.
- Gemini failures never stop subtitles; fallback to whisper-only timestamps.
