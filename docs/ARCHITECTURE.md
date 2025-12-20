# Architecture (v1.6.2)

## Overview

ShortVideo V1 is a FastAPI gateway that creates video-processing tasks and runs a four-step pipeline (parse → subtitles → dub → pack). It exposes HTML pages for operators, JSON APIs for task management, and file-serving routes for artifacts.

## Repo Layout (SSOT)

The repository layout in `docs/REPO_STRUCTURE.md` is the single source of truth for the current code layout.

## Runtime Components

- **FastAPI app (primary entrypoint)**: `gateway/main.py` exposes `/v1`, `/api`, `/tasks`, `/files`, `/admin/tools` routes.
- **Secondary app (legacy)**: `gateway/app/main.py` exists with similar routes; SSOT for runtime paths is `gateway/main.py`.
- **Database**: SQLAlchemy with SQLite by default (`gateway/app/db.py`).
- **Workspace**: filesystem paths under `workspace_root` (from `gateway/app/config.py`).
- **External services**: parser provider (Xiongmao), subtitles (Gemini/OpenAI), dubbing (LOVO/Edge-TTS).

## Data Model

### Task (DB: `gateway/app/models.py`)

Core fields:

- `id`, `title`, `source_url`, `platform`
- `account_id`, `account_name`
- `video_type`, `template`
- `category_key`, `content_lang`, `ui_lang`, `style_preset`, `face_swap_enabled`
- `status`, `last_step`, `duration_sec`, `thumb_url`
- `raw_path`, `mm_audio_path`, `pack_path`
- `error_message`, `error_reason`
- Provider fields: `parse_provider`, `subtitles_provider`, `dub_provider`, `pack_provider`, `face_swap_provider`
- `created_at`, `updated_at`

### provider_config (DB: `gateway/app/db.py`)

Key-value store used by Admin Tools:

- `key` (TEXT, primary key)
- `value` (TEXT)
- `updated_at` (TEXT)

Key format examples:

- `parse_provider`, `parse_enabled`
- `subtitles_provider`, `subtitles_enabled`
- `dub_provider`, `dub_enabled`
- `pack_provider`, `pack_enabled`
- `face_swap_provider`, `face_swap_enabled`

## Workspace Layout

**SSOT**: `gateway/app/core/workspace.py`.

- `workspace_root`: from `gateway/app/config.py` (`WORKSPACE_ROOT` env, default `/opt/render/project/src/video_workspace/tv1_validation`).
- Per-task directory: `workspace_root/tasks/<task_id>/`
  - `raw/<task_id>.mp4`
  - `subs/<task_id>_origin.srt`
  - `subs/<task_id>_mm.srt` (or `_my.srt` fallback)
  - `audio/<task_id>_mm.wav` or `<task_id>_mm.mp3`
- Pack output: `workspace_root/pack/<task_id>_capcut_pack.zip`
- Other directories: `workspace_root/deliver`, `workspace_root/assets`, `workspace_root/tmp`

## Pipeline Orchestration

**SSOT**:

- Orchestration: `gateway/app/services/pipeline_v1.py`
- Step execution: `gateway/app/services/steps_v1.py`

Flow:

1. `run_pipeline_for_task()` loads the task, sets `status="processing"`.
2. Calls `run_parse_step()` → `run_subtitles_step()` → `run_dub_step()` → `run_pack_step()`.
3. `steps_v1.py` persists output fields (`raw_path`, `origin_srt_path`, `mm_srt_path`, `mm_audio_path`, `pack_path`).
4. `run_pack_step()` sets `status="ready"`, `last_step="pack"`, and clears error fields.

## Task State Machine

**SSOT**: `gateway/app/services/steps_v1.py` + `gateway/app/services/pipeline_v1.py`.

- `pending` → `processing` → `ready`
- `error` when a step fails or is disabled
- `last_step`: `parse`, `subtitles`, `dub`, `pack`

## Providers & Tools

**SSOT**: `gateway/app/providers/registry.py` and `gateway/routes/admin_tools.py`.

Available providers (registry):

- `parse`: `xiongmao`, `xiaomao`
- `subtitles`: `gemini`, `whisper`
- `dub`: `lovo`, `edge-tts`
- `pack`: `capcut`, `youcut`
- `face_swap`: `none`, `xxx_faceswap_api`

Admin Tools API uses `provider_config` to store overrides.

## Failure Modes & Debugging

- **Pack status stuck**: if `pack_path` is empty or `status` not updated, verify `run_pack_step()` updates DB (`steps_v1.py`) and that `pack_zip_path()` points to `workspace_root/pack/`.
- **Stale Task Board status**: check `/api/tasks` output directly and confirm polling + cache busting in `gateway/app/templates/tasks.html`.
- **Bad source URL navigation**: ensure only extracted http(s) URLs are clickable and raw share text is shown as text, not href.

## SSOT Rules

- **Workspace paths** are defined only in `gateway/app/core/workspace.py`.
- **Provider defaults and availability** are defined only in `gateway/app/providers/registry.py`.
- **Status and artifact writebacks** happen only in `gateway/app/services/steps_v1.py` and `gateway/app/services/pipeline_v1.py`.
