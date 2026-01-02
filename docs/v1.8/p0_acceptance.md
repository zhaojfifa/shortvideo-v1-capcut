# v1.8 P0 Acceptance Criteria

## Manual verification (Render)
- Task Workbench: clicking Generate subtitles must call `POST /api/tasks/{task_id}/subtitles` (not `/v1/subtitles`).
- Subtitles: run `POST /api/tasks/{task_id}/subtitles`; must succeed without 500; `origin.srt` + `subtitles.json` exist.
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
