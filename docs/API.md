# API Reference (v1.6.2)

## UI Pages

| Method | Path | Description | Request | Response | Notes |
| --- | --- | --- | --- | --- | --- |
| GET | `/ui` | Pipeline lab UI | — | HTML | `gateway/routes/v1.py` and `gateway/app/templates/pipeline_lab.html` |
| GET | `/tasks` | Task Board | — | HTML | `gateway/app/routers/tasks.py` |
| GET | `/tasks/new` | New Suitcase Task | — | HTML | `gateway/app/templates/tasks_new.html` |
| GET | `/tasks/{task_id}` | Task Workbench | — | HTML | `gateway/app/templates/task_workbench.html` |
| GET | `/admin/tools` | Admin Tools | — | HTML | `gateway/routes/admin_tools.py` |

## Task APIs

| Method | Path | Description | Request | Response | Notes |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/tasks` | Create task | JSON body (`TaskCreate`) | `TaskDetail` | Accepts raw `source_url` text |
| GET | `/api/tasks` | List tasks | `limit`, `page`, `status`, `account_id` | `TaskListResponse` | `limit` is alias for `page_size` |
| GET | `/api/tasks/{task_id}` | Get task | — | `TaskDetail` | Includes artifact paths + provider fields |

## V1 Step APIs

| Method | Path | Description | Request | Response | Notes |
| --- | --- | --- | --- | --- | --- |
| POST | `/v1/parse` | Parse + download raw video | `ParseRequest` | JSON | Uses V1 parser; stores raw artifact |
| POST | `/v1/subtitles` | Transcribe + translate | `SubtitlesRequest` | JSON | Writes origin/mm SRT |
| POST | `/v1/dub` | Generate dubbing audio | `DubRequest` | JSON | Writes mm audio |
| POST | `/v1/pack` | Build CapCut pack | `PackRequest` | JSON | Writes pack zip + marks task ready |
| POST | `/v1/publish` | Publish CapCut pack | `PublishRequest` | `PublishResponse` | Uploads to R2 or local archive |

## V1 Artifact Downloads

| Method | Path | Description | Request | Response | Notes |
| --- | --- | --- | --- | --- | --- |
| GET | `/v1/tasks/{task_id}/raw` | Raw MP4 | — | MP4 | `raw_path` indicates presence |
| GET | `/v1/tasks/{task_id}/subs_origin` | Origin SRT | — | SRT | `origin_srt_path` indicates presence |
| GET | `/v1/tasks/{task_id}/subs_mm` | Burmese SRT | — | SRT | `mm_srt_path` indicates presence |
| GET | `/v1/tasks/{task_id}/audio_mm` | Dubbed audio | — | Audio | `mm_audio_path` indicates presence |
| GET | `/v1/tasks/{task_id}/pack` | CapCut pack ZIP | — | Redirect | Redirects to published R2/public URL or `/files/...` |

## Admin Tools APIs

| Method | Path | Description | Request | Response | Notes |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/admin/tools` | Provider defaults | — | JSON | Returns `tools` with provider + enabled |
| POST | `/api/admin/tools` | Save defaults | JSON payload | JSON | Validates provider names |
| POST | `/api/admin/publish/backfill` | Publish backfill | Query params | JSON | Publishes latest packs (admin) |

## File Serving

| Method | Path | Description | Request | Response | Notes |
| --- | --- | --- | --- | --- | --- |
| GET | `/files/{rel_path:path}` | Workspace file access | — | File | `rel_path` must be under `raw/`, `tasks/`, `audio/`, `pack/`, or `published/` |

## cURL Examples

### Create task

```bash
curl -s -X POST "http://127.0.0.1:8000/api/tasks" \
  -H "Content-Type: application/json" \
  -d '{"source_url":"share text https://v.douyin.com/abc","platform":"douyin"}'
```

### List tasks

```bash
curl -s "http://127.0.0.1:8000/api/tasks?limit=5"
```

### Get task

```bash
curl -s "http://127.0.0.1:8000/api/tasks/<task_id>"
```

### Parse

```bash
curl -s -X POST "http://127.0.0.1:8000/v1/parse" \
  -H "Content-Type: application/json" \
  -d '{"task_id":"<task_id>","platform":"douyin","link":"https://www.douyin.com/video/..."}'
```

### Subtitles

```bash
curl -s -X POST "http://127.0.0.1:8000/v1/subtitles" \
  -H "Content-Type: application/json" \
  -d '{"task_id":"<task_id>","target_lang":"my"}'
```

### Dub

```bash
curl -s -X POST "http://127.0.0.1:8000/v1/dub" \
  -H "Content-Type: application/json" \
  -d '{"task_id":"<task_id>","voice_id":"mm_female_1"}'
```

### Pack

```bash
curl -s -X POST "http://127.0.0.1:8000/v1/pack" \
  -H "Content-Type: application/json" \
  -d '{"task_id":"<task_id>"}'
```

### Publish pack

```bash
curl -s -X POST "http://127.0.0.1:8000/v1/publish" \
  -H "Content-Type: application/json" \
  -d '{"task_id":"<task_id>","force":false}'
```

### Download pack (stable link)

```bash
curl -s -L -O "http://127.0.0.1:8000/v1/tasks/<task_id>/pack"
```
