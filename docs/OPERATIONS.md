# Operations Guide (v1.6.2)

## Render Deployment

- **Entrypoint**: `uvicorn gateway.main:app --host 0.0.0.0 --port 8000`
- **Workspace root**: `WORKSPACE_ROOT` (default from `gateway/app/config.py`: `/opt/render/project/src/video_workspace/tv1_validation`)
- **Database**: uses SQLite by default (`sqlite:///./shortvideo.db` in `gateway/app/db.py`).

## Environment Variables

Refer to `.env.example` for all environment variables. Key ones:

- `WORKSPACE_ROOT`: filesystem root for task artifacts
- `XIONGMAO_API_KEY`: required for parse provider
- `OPENAI_API_KEY`, `GEMINI_API_KEY`, `LOVO_API_KEY`: optional providers
- `FEATURE_PACK_DOWNLOAD` (default `true`)
- `FEATURE_ASSET_DOWNLOAD` (default `true`)
- `FEATURE_PUBLISH_BACKFILL` (default `false`)
- `PUBLISH_PROVIDER` (default `local`)

R2 publish configuration (required when `PUBLISH_PROVIDER=r2`):

- `R2_ENDPOINT_URL`
- `R2_BUCKET`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_PUBLIC_BASE_URL` (optional; if unset, presigned URLs are used)

## Persistence Strategy

- **SQLite**: if used on Render, ensure the DB file is stored on a persistent disk.
- **Workspace**: ensure `WORKSPACE_ROOT` points to a persistent volume if artifacts must survive restarts.

## Logs & Troubleshooting

- **Task JSON**: `/api/tasks/<task_id>` is the authoritative view of status, pack_path, and errors.
- **Pipeline errors**: check `error_message` and `error_reason` in task JSON.
- **Provider failures**: check Render logs for upstream API errors (e.g. Xiongmao).

## Health & Smoke Checklist

- `GET /tasks` returns HTML
- `GET /ui` returns HTML
- `GET /api/tasks?limit=1` returns JSON
- `POST /v1/parse` returns JSON
- `POST /v1/pack` eventually yields `status: ready` in `/api/tasks/<task_id>`
- `POST /v1/publish` returns JSON
- `GET /v1/tasks/<task_id>/pack` returns a 302 redirect

## Publish backfill

To backfill existing tasks with pack artifacts:

```bash
python -m gateway.app.scripts.backfill_publish --limit 5
```

## Mobile access

Use the mobile-prefixed routes when training mobile operators:

- `/m/tasks`
- `/m/tasks/new`
- `/m/tasks/{task_id}`

## Task board UI behavior

- Task board labels render in both primary and secondary languages when `UI_SHOW_SECONDARY=true`.
- Category and status values are translated via i18n keys (e.g., suitcase/beauty, ready/processing/pending/error).
- Status badges include an inline legend on the task list page to explain color meanings.
- The task count and empty-state copy are bilingual when secondary language display is enabled.

## Feature Flags

Feature flags are injected into HTML templates via `window.__FEATURES__`.

Defaults:

- `FEATURE_ALLOW_PACK_DOWNLOAD=true`
- `FEATURE_SHOW_ADMIN_TOOLS=true`
- `FEATURE_ENABLE_AUTO_PIPELINE=true`

Smoke commands:

```bash
python -m compileall gateway
curl -I https://<host>/tasks
curl -s https://<host>/api/tasks?limit=1 | jq
```
