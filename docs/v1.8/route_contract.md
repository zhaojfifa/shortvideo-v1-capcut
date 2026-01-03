# v1.8 Route Contract (UI vs Pipeline)

Rule A (Task Workbench)
- Pages under `/tasks` must call action endpoints under `/api/tasks/{task_id}/...`.
- Downloads stay under `/v1/tasks/{task_id}/...` and must return 302 to presigned URLs.

Rule B (Pipeline Lab)
- `/ui` must call legacy action endpoints under `/v1/...` (parse/subtitles/dub/pack).
- Downloads stay under `/v1/tasks/{task_id}/...`.

Rule C (No duplicate downloads)
- Do not include `gateway/routes/v1.py` in the main app router.
- If v1 actions are needed, use a thin `gateway/routes/v1_actions.py` router (POST only).
