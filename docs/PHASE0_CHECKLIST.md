# Phase0 Regression Checklist

Use this checklist for every Phase0 PR. All curl commands should be deterministic and recorded in the PR description.

## API checks

### Create task
```bash
curl -sS -X POST "$BASE_URL/api/tasks" \
  -H "content-type: application/json" \
  -d '{"source_url":"https://www.douyin.com/video/123","platform":"douyin","account_id":"x","account_name":"x","video_type":"comparison","template":"suitcase","category_key":"beauty","content_lang":"my","ui_lang":"zh","style_preset":"fast"}'
```

### List tasks
```bash
curl -sS "$BASE_URL/api/tasks?limit=50"
```

### Get task by id
```bash
curl -sS "$BASE_URL/api/tasks/{task_id}"
```

### (If exists) Publish + backfill validation
```bash
curl -sS -X POST "$BASE_URL/v1/publish" \
  -H "content-type: application/json" \
  -d '{"task_id":"<task_id>","provider":"<provider>","payload":{}}'

curl -sS "$BASE_URL/api/tasks/{task_id}" | jq '.publish_status,.publish_provider,.publish_key,.publish_url,.published_at'
```

## Regression cases

- **R0: End-to-end + persistence after restart**
  - Create a task, confirm it appears in list.
  - Restart the service, confirm the task is still listed.

- **R1: Namespace isolation (if artifact storage exists)**
  - Verify task artifacts are scoped per tenant or namespace if storage supports it.

- **R2: Template/UI freeze check**
  - Ensure no diffs under `static/templates/**` and `gateway/app/static/ui.html` unless a dedicated V1-UI PR is explicitly scoped.

## Notes

- Set `BASE_URL` to the target environment, e.g. `https://shortvideo-v1-capcut.onrender.com`.
- Record outputs or relevant snippets in the PR description.
