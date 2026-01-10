"""Task API and HTML routers for the gateway application."""

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel

from ..config import get_settings
from ..core.features import get_features
from ..schemas import (
    DubRequest,
    PackRequest,
    ParseRequest,
    SubtitlesRequest,
    TaskCreate,
    TaskDetail,
    TaskListResponse,
    TaskSummary,
)

from gateway.app.web.templates import get_templates
from gateway.app.deps import get_task_repository  # 只保留这一处依赖注入入口

# Ports / typing
from gateway.ports.repository import ITaskRepository  # 如路径不对，按你们 ports 实际文件修

# Canonical SSOT dubbing step (v1.62+)
from gateway.app.steps.dubbing import run_dub_step as run_dub_step_ssot

# Legacy v1 pipeline steps (parse/subtitles/pack). Dubbing 保留 v1 名称但必须显式别名，避免覆盖 SSOT
from ..services.steps_v1 import (
    run_pack_step as run_pack_step_v1,
    run_parse_step as run_parse_step_v1,
    run_subtitles_step as run_subtitles_step_v1,
    run_dub_step as run_dub_step_v1,
)
def coerce_datetime(v: Any) -> Optional[datetime]:
    """
    Best-effort convert repository stored value into a timezone-aware datetime.
    Accepts:
      - datetime (naive/aware)
      - ISO8601 string (with/without 'Z', with/without timezone)
      - epoch seconds/ms (int/float or numeric string)
    Returns:
      - datetime (tz-aware, UTC) or None if cannot parse
    """
    if v is None:
        return None

    # already datetime
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)

    # epoch seconds / milliseconds
    if isinstance(v, (int, float)):
        ts = float(v)
        if ts > 1e12:  # ms
            ts = ts / 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            return None

    # strings
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None

        # numeric string -> epoch
        if s.isdigit():
            try:
                ts = float(s)
                if ts > 1e12:
                    ts = ts / 1000.0
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            except Exception:
                return None

        # ISO8601 variants
        # handle "Z"
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"

        # allow "YYYY-mm-dd HH:MM:SS" -> fromisoformat can parse, but ensure 'T' optional ok
        try:
            dt = datetime.fromisoformat(s)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    # unknown type
    return None


def coerce_datetime_or_epoch(v: Any) -> datetime:
    """
    Safe non-null datetime for response models that disallow None.
    """
    return coerce_datetime(v) or datetime(1970, 1, 1, tzinfo=timezone.utc)

# Artifact storage helpers（只 import 一次，禁止在文件底部重定义同名函数）
from gateway.app.services.artifact_storage import (
    upload_task_artifact,
    get_download_url,
    get_object_bytes,
    object_exists,
)
from gateway.app.services.scene_split import enqueue_scenes_build
from gateway.app.services.publish_service import publish_task_pack, resolve_download_url
from gateway.app.db import SessionLocal

from gateway.app.task_repo_utils import normalize_task_payload, sort_tasks_by_created
from gateway.app.services.task_cleanup import delete_task_record, purge_task_artifacts

from ..core.workspace import (
    Workspace,
    origin_srt_path,
    deliver_pack_zip_path,
    raw_path,
    relative_to_workspace,
    task_base_dir,
)

logger = logging.getLogger(__name__)



class DubProviderRequest(BaseModel):
    provider: str | None = None
    voice_id: str | None = None


class EditedTextRequest(BaseModel):
    text: str


class ScenesRequest(BaseModel):
    force: bool = False


class SubtitlesTaskRequest(BaseModel):
    target_lang: str | None = None
    force: bool = False
    translate: bool = True


class ParseTaskRequest(BaseModel):
    platform: str | None = None


class PublishTaskRequest(BaseModel):
    provider: str | None = None
    force: bool = False


pages_router = APIRouter()
api_router = APIRouter(prefix="/api", tags=["tasks"])
templates = get_templates()
def _coerce_datetime(value) -> datetime:
    # Pydantic TaskDetail.created_at expects datetime, so guarantee it.
    if isinstance(value, datetime):
        return value

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return datetime.now(timezone.utc)

        # unix seconds in string
        if s.isdigit():
            return datetime.fromtimestamp(int(s), tz=timezone.utc)

        # ISO with Z
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"

        # Try ISO formats
        try:
            dt = datetime.fromisoformat(s)
            # If naive, assume UTC
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass

        # Common fallback: "YYYY-MM-DD HH:MM:SS"
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)

    return datetime.now(timezone.utc)


def _infer_platform_from_url(url: str) -> Optional[str]:
    url_lower = url.lower()
    if "douyin.com" in url_lower:
        return "douyin"
    if "tiktok.com" in url_lower:
        return "tiktok"
    if "xiaohongshu.com" in url_lower or "xhslink.com" in url_lower:
        return "xhs"
    if "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "facebook"
    return None


def _is_storage_key(value: Optional[str]) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return lowered.startswith(("http://", "https://", "s3://", "r2://"))


def _pack_path_for_list(task: dict) -> Optional[str]:
    task_id = str(_task_value(task, "task_id") or _task_value(task, "id") or "")
    pack_type = _task_value(task, "pack_type")
    pack_key = _task_value(task, "pack_key")
    pack_path = _task_value(task, "pack_path")
    if pack_type == "capcut_v18" and pack_key:
        return str(pack_key)
    if pack_path:
        pack_path = str(pack_path)
        if pack_path.startswith(("pack/", "published/")) and not _is_storage_key(pack_path):
            return pack_path
    pack_file = deliver_pack_zip_path(task_id)
    if pack_file.exists():
        return relative_to_workspace(pack_file)
    return None


def _mm_edited_path(task_id: str) -> Path:
    return task_base_dir(task_id) / "mm_edited.txt"


def _load_dub_text(task_id: str) -> tuple[str, str]:
    edited_path = _mm_edited_path(task_id)
    if edited_path.exists():
        text = edited_path.read_text(encoding="utf-8").strip()
        if text:
            return text, "mm_edited"
    workspace = Workspace(task_id)
    mm_txt_path = workspace.mm_srt_path.with_suffix(".txt")
    if mm_txt_path.exists():
        return mm_txt_path.read_text(encoding="utf-8"), "mm_txt"
    return "", "mm_txt"


def _resolve_text_path(task_id: str, kind: str) -> Path | None:
    td = task_base_dir(task_id)
    ws = Workspace(task_id)

    if kind == "mm_edited":
        p = _mm_edited_path(task_id)
        return p if p.exists() else None

    if kind == "mm_txt":
        p = ws.mm_srt_path.with_suffix(".txt")
        if p.exists():
            return p
        p2 = td / "mm.txt"
        return p2 if p2.exists() else None

    if kind == "origin_srt":
        candidates: list[Path] = []
        origin_attr = getattr(ws, "origin_srt_path", None)
        if isinstance(origin_attr, Path):
            candidates.append(origin_attr)
        candidates.extend(
            [
                td / "origin.srt",
                td / "subs_origin.srt",
                td / "subs_origin.txt",
            ]
        )
        for c in candidates:
            if c and c.exists():
                return c
        return None

    if kind == "mm_srt":
        p = ws.mm_srt_path
        if p.exists():
            return p
        p2 = td / "mm.srt"
        return p2 if p2.exists() else None

    return None


@pages_router.get("/tasks", response_class=HTMLResponse)
async def tasks_page(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    repo=Depends(get_task_repository),
):
    """Render the task board HTML page."""

    db_tasks = sort_tasks_by_created(repo.list())

    rows: list[dict] = []
    for t in db_tasks[:limit]:
        rows.append(
            {
                "task_id": t.get("task_id") or t.get("id"),
                "platform": t.get("platform"),
                "source_url": t.get("source_url"),
                "title": t.get("title") or "",
                "category_key": t.get("category_key") or "",
                "content_lang": t.get("content_lang") or "",
                "status": t.get("status") or "pending",
                "created_at": t.get("created_at") or "",
                "pack_path": _pack_path_for_list(t),
                "ui_lang": t.get("ui_lang") or "",
            }
        )

    return templates.TemplateResponse(
        "tasks.html",
        {"request": request, "tasks": rows, "features": get_features()},
    )


@pages_router.get("/tasks/new", response_class=HTMLResponse)
async def tasks_new(request: Request) -> HTMLResponse:
    """Render suitcase quick-create page."""

    return templates.TemplateResponse(
        "tasks_new.html",
        {"request": request, "features": get_features()},
    )


@pages_router.get("/ui", response_class=HTMLResponse)
async def pipeline_lab(request: Request) -> HTMLResponse:
    settings = get_settings()
    env_summary = {
        "workspace_root": settings.workspace_root,
        "douyin_api_base": getattr(settings, "douyin_api_base", ""),
        "whisper_model": getattr(settings, "whisper_model", ""),
        "gpt_model": getattr(settings, "gpt_model", ""),
        "asr_backend": getattr(settings, "asr_backend", None) or "whisper",
        "subtitles_backend": getattr(settings, "subtitles_backend", None) or "gemini",
        "gemini_model": getattr(settings, "gemini_model", ""),
    }
    return templates.TemplateResponse(
        "pipeline_lab.html",
        {"request": request, "env_summary": env_summary},
    )


@pages_router.get("/v1/tasks/{task_id}/raw")
def download_raw(task_id: str, repo=Depends(get_task_repository)):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="raw video not found")
    key = _require_storage_key(task, "raw_path", "raw video not found")
    return RedirectResponse(url=get_download_url(key), status_code=302)


@pages_router.get("/v1/tasks/{task_id}/subs_origin")
def download_origin_subs(
    task_id: str,
    inline: bool = Query(default=False),
    repo=Depends(get_task_repository),
):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="origin subtitles not found")
    key = _require_storage_key(task, "origin_srt_path", "origin subtitles not found")
    return _text_or_redirect(key, inline=inline)


@pages_router.get("/v1/tasks/{task_id}/subs_mm")
def download_mm_subs(
    task_id: str,
    inline: bool = Query(default=False),
    repo=Depends(get_task_repository),
):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="burmese subtitles not found")
    key = _require_storage_key(task, "mm_srt_path", "burmese subtitles not found")
    return _text_or_redirect(key, inline=inline)


@pages_router.get("/v1/tasks/{task_id}/mm_txt")
def download_mm_txt(
    task_id: str,
    inline: bool = Query(default=False),
    repo=Depends(get_task_repository),
):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="mm txt not found")
    mm_key = _require_storage_key(task, "mm_srt_path", "mm txt not found")
    txt_key = mm_key[:-4] + ".txt" if mm_key.endswith(".srt") else f"{mm_key}.txt"
    if not object_exists(txt_key):
        raise HTTPException(status_code=404, detail="mm txt not found")
    return _text_or_redirect(txt_key, inline=inline)


@pages_router.get("/v1/tasks/{task_id}/audio_mm")
def download_audio_mm(task_id: str, repo=Depends(get_task_repository)):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="dubbed audio not found")
    key = _require_storage_key(task, "mm_audio_path", "dubbed audio not found")
    return RedirectResponse(url=get_download_url(key), status_code=302)


@pages_router.get("/v1/tasks/{task_id}/pack")
def download_pack(task_id: str, repo=Depends(get_task_repository)):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Pack not found")
    pack_type = _task_value(task, "pack_type")
    if pack_type == "capcut_v18":
        pack_key = _task_value(task, "pack_key") or _task_value(task, "pack_path")
        if not pack_key or not object_exists(str(pack_key)):
            raise HTTPException(status_code=404, detail="Pack not found")
        return RedirectResponse(url=get_download_url(str(pack_key)), status_code=302)

    key = _task_value(task, "pack_key") or _task_value(task, "pack_path")
    if not key or not object_exists(str(key)):
        raise HTTPException(status_code=404, detail="Pack not found")
    return RedirectResponse(url=get_download_url(str(key)), status_code=302)


@pages_router.get("/v1/tasks/{task_id}/scenes")
def download_scenes(task_id: str, repo=Depends(get_task_repository)):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Scenes not found")
    scenes_key = _task_value(task, "scenes_key")
    if not scenes_key or not object_exists(str(scenes_key)):
        raise HTTPException(status_code=404, detail="Scenes not ready")
    return RedirectResponse(url=get_download_url(str(scenes_key)), status_code=302)


@pages_router.get("/v1/tasks/{task_id}/status")
def task_status(task_id: str, repo=Depends(get_task_repository)):
    task = repo.get(task_id)
    if not task:
        workspace = Workspace(task_id)
        mm_txt_path = workspace.mm_srt_path.with_suffix(".txt")
        scenes_zip = Path("deliver") / "scenes" / task_id / "scenes.zip"
        pack_zip = deliver_pack_zip_path(task_id)
        return {
            "task_id": task_id,
            "status": None,
            "last_step": None,
            "subtitles_status": None,
            "subtitles_error": None,
            "dub_status": None,
            "dub_error": None,
            "pack_status": None,
            "pack_error": None,
            "scenes_status": None,
            "scenes_error": None,
            "raw_exists": workspace.raw_video_exists(),
            "origin_srt_exists": workspace.origin_srt_path.exists(),
            "mm_srt_exists": workspace.mm_srt_exists(),
            "mm_txt_exists": mm_txt_path.exists(),
            "mm_audio_exists": workspace.mm_audio_exists(),
            "pack_exists": pack_zip.exists(),
            "scenes_exists": scenes_zip.exists(),
        }

    raw_key = _task_key(task, "raw_path")
    origin_key = _task_key(task, "origin_srt_path")
    mm_key = _task_key(task, "mm_srt_path")
    mm_txt_key = None
    if mm_key and mm_key.endswith(".srt"):
        mm_txt_key = f"{mm_key[:-4]}.txt"
    audio_key = _task_key(task, "mm_audio_path")
    pack_key = _task_key(task, "pack_key") or _task_key(task, "pack_path")
    scenes_key = _task_key(task, "scenes_key")

    return {
        "task_id": str(_task_value(task, "task_id") or _task_value(task, "id") or task_id),
        "status": _task_value(task, "status"),
        "last_step": _task_value(task, "last_step"),
        "subtitles_status": _task_value(task, "subtitles_status"),
        "subtitles_error": _task_value(task, "subtitles_error"),
        "dub_status": _task_value(task, "dub_status"),
        "dub_error": _task_value(task, "dub_error"),
        "pack_status": _task_value(task, "pack_status"),
        "pack_error": _task_value(task, "pack_error"),
        "scenes_status": _task_value(task, "scenes_status"),
        "scenes_error": _task_value(task, "scenes_error"),
        "raw_exists": bool(raw_key and object_exists(raw_key)),
        "origin_srt_exists": bool(origin_key and object_exists(origin_key)),
        "mm_srt_exists": bool(mm_key and object_exists(mm_key)),
        "mm_txt_exists": bool(mm_txt_key and object_exists(mm_txt_key)),
        "mm_audio_exists": bool(audio_key and object_exists(audio_key)),
        "pack_exists": bool(pack_key and object_exists(pack_key)),
        "scenes_exists": bool(scenes_key and object_exists(scenes_key)),
    }




def _task_endpoint(task_id: str, kind: str) -> Optional[str]:
    safe_id = str(task_id)
    if kind == "raw":
        return f"/v1/tasks/{safe_id}/raw"
    if kind == "origin":
        return f"/v1/tasks/{safe_id}/subs_origin"
    if kind == "mm":
        return f"/v1/tasks/{safe_id}/subs_mm"
    if kind == "mm_txt":
        return f"/v1/tasks/{safe_id}/mm_txt"
    if kind == "audio":
        return f"/v1/tasks/{safe_id}/audio_mm"
    if kind == "pack":
        return f"/v1/tasks/{safe_id}/pack"
    if kind == "scenes":
        return f"/v1/tasks/{safe_id}/scenes"
    return None


def _task_value(task: dict, field: str) -> Optional[str]:
    if isinstance(task, dict):
        return task.get(field)
    return getattr(task, field, None)


def _task_key(task: dict, field: str) -> Optional[str]:
    value = _task_value(task, field)
    return str(value) if value else None


def _require_storage_key(task: dict, field: str, not_found: str) -> str:
    key = _task_key(task, field)
    if not key or not object_exists(key):
        raise HTTPException(status_code=404, detail=not_found)
    return key


def _text_or_redirect(key: str, inline: bool) -> Response:
    if inline:
        data = get_object_bytes(key)
        if data is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return Response(content=data, media_type="text/plain; charset=utf-8")
    return RedirectResponse(url=get_download_url(key), status_code=302)


def _resolve_download_urls(task: dict) -> dict[str, Optional[str]]:
    task_id = str(task.get("task_id") or task.get("id"))
    raw_url = _task_endpoint(task_id, "raw") if task.get("raw_path") else None
    origin_url = (
        _task_endpoint(task_id, "origin")
        if task.get("origin_srt_path")
        else None
    )
    mm_url = (
        _task_endpoint(task_id, "mm")
        if task.get("mm_srt_path")
        else None
    )
    audio_url = (
        _task_endpoint(task_id, "audio")
        if task.get("mm_audio_path")
        else None
    )
    mm_txt_url = _task_endpoint(task_id, "mm_txt") if mm_url else None
    pack_key = task.get("pack_key")
    pack_type = task.get("pack_type")
    pack_url = None
    if pack_type == "capcut_v18" and pack_key:
        pack_url = _task_endpoint(task_id, "pack")
    elif task.get("pack_path"):
        pack_url = _task_endpoint(task_id, "pack")
    scenes_url = _task_endpoint(task_id, "scenes") if task.get("scenes_key") else None

    return {
        "raw_path": raw_url,
        "origin_srt_path": origin_url,
        "mm_srt_path": mm_url,
        "mm_audio_path": audio_url,
        "mm_txt_path": mm_txt_url,
        "pack_path": pack_url,
        "scenes_path": scenes_url,
    }

def _model_allowed_fields(model_cls) -> set[str]:
    # pydantic v2: model_fields; v1: __fields__
    if hasattr(model_cls, "model_fields"):
        return set(model_cls.model_fields.keys())
    if hasattr(model_cls, "__fields__"):
        return set(model_cls.__fields__.keys())
    return set()

def _task_to_detail(task: dict) -> TaskDetail:
    paths = _resolve_download_urls(task)
    status = task.get("status") or "pending"
    if status != "error" and paths.get("pack_path"):
        status = "ready"

    payload = {
        "task_id": str(task.get("task_id") or task.get("id")),
        "title": task.get("title"),
        "source_url": str(task.get("source_url")) if task.get("source_url") else None,
        "source_link_url": _extract_first_http_url(task.get("source_url")),
        "platform": task.get("platform"),
        "account_id": task.get("account_id"),
        "account_name": task.get("account_name"),
        "video_type": task.get("video_type"),
        "template": task.get("template"),
        "category_key": task.get("category_key") or "beauty",
        "content_lang": task.get("content_lang") or "my",
        "ui_lang": task.get("ui_lang") or "en",
        "style_preset": task.get("style_preset"),
        "face_swap_enabled": bool(task.get("face_swap_enabled")),
        "status": status,
        "last_step": task.get("last_step"),
        "duration_sec": task.get("duration_sec"),
        "thumb_url": task.get("thumb_url"),

        "raw_path": paths.get("raw_path"),
        "origin_srt_path": paths.get("origin_srt_path"),
        "mm_srt_path": paths.get("mm_srt_path"),
        "mm_audio_path": paths.get("mm_audio_path"),
        "pack_path": paths.get("pack_path"),
        "scenes_path": paths.get("scenes_path"),
        "scenes_status": task.get("scenes_status"),
        "scenes_key": task.get("scenes_key"),
        "scenes_error": task.get("scenes_error"),
        "subtitles_status": task.get("subtitles_status"),
        "subtitles_key": task.get("subtitles_key"),
        "subtitles_error": task.get("subtitles_error"),

        "created_at": _coerce_datetime(task.get("created_at") or task.get("created") or task.get("createdAt")),
        "updated_at": _coerce_datetime(task.get("updated_at") or task.get("updatedAt")),
        "error_message": task.get("error_message"),
        "error_reason": task.get("error_reason"),

        # 下面这些字段如果 TaskDetail 没定义，会被过滤掉，不再触发 500
        "parse_provider": task.get("parse_provider"),
        "subtitles_provider": task.get("subtitles_provider"),
        "dub_provider": task.get("dub_provider"),
        "pack_provider": task.get("pack_provider"),
        "face_swap_provider": task.get("face_swap_provider"),
        "publish_status": task.get("publish_status"),
        "publish_provider": task.get("publish_provider"),
        "publish_key": task.get("publish_key"),
        "publish_url": task.get("publish_url"),
        "published_at": task.get("published_at"),
        "priority": task.get("priority"),
        "assignee": task.get("assignee"),
        "ops_notes": task.get("ops_notes"),
    }

    allowed = _model_allowed_fields(TaskDetail)
    payload = {k: v for k, v in payload.items() if k in allowed}
    return TaskDetail(**payload)


def _extract_first_http_url(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"https?://\S+", text)
    return match.group(0) if match else None


def _repo_upsert(repo, task_id: str, patch: dict) -> None:
    repo.upsert(task_id, patch)


def _run_pipeline_background(task_id: str, repo) -> None:
    task = repo.get(task_id)
    if not task:
        logger.error("Task %s not found in repository, abort pipeline", task_id)
        return

    status_update = {
        "status": "processing",
        "error_message": None,
        "error_reason": None,
    }

    default_lang = os.getenv("DEFAULT_MM_LANG", "my")
    default_voice = os.getenv("DEFAULT_MM_VOICE_ID", "mm_female_1")
    target_lang = task.get("content_lang") or default_lang
    voice_id = task.get("voice_id") or default_voice

    current_step = "parse"
    try:
        _repo_upsert(repo, task_id, {**status_update, "last_step": current_step})
        parse_req = ParseRequest(
            task_id=task_id,
            platform=task.get("platform"),
            link=task.get("source_url") or task.get("link") or "",
        )
        parse_res = asyncio.run(run_parse_step_v1(parse_req))
        raw_file = raw_path(task_id)
        raw_key = None
        if raw_file.exists():
            raw_key = upload_task_artifact(task, raw_file, "raw.mp4", task_id=task_id)
        duration_sec = parse_res.get("duration_sec") if isinstance(parse_res, dict) else None
        _repo_upsert(
            repo,
            task_id,
            {
                **status_update,
                "last_step": current_step,
                "raw_path": raw_key,
                "duration_sec": duration_sec,
            },
        )

        current_step = "subtitles"
        _repo_upsert(repo, task_id, {**status_update, "last_step": current_step})
        subs_req = SubtitlesRequest(
            task_id=task_id,
            target_lang=target_lang,
            force=False,
            translate=True,
            with_scenes=True,
        )
        asyncio.run(run_subtitles_step_v1(subs_req))
        workspace = Workspace(task_id)
        origin_key = (
            upload_task_artifact(task, workspace.origin_srt_path, "origin.srt", task_id=task_id)
            if workspace.origin_srt_path.exists()
            else None
        )
        mm_key = (
            upload_task_artifact(task, workspace.mm_srt_path, "mm.srt", task_id=task_id)
            if workspace.mm_srt_path.exists()
            else None
        )
        mm_txt_path = workspace.mm_srt_path.with_suffix(".txt")
        if mm_txt_path.exists():
            upload_task_artifact(task, mm_txt_path, "mm.txt", task_id=task_id)
        _repo_upsert(
            repo,
            task_id,
            {
                **status_update,
                "last_step": current_step,
                "origin_srt_path": origin_key,
                "mm_srt_path": mm_key,
            },
        )

        current_step = "dub"
        _repo_upsert(repo, task_id, {**status_update, "last_step": current_step})
        dub_req = DubRequest(
            task_id=task_id,
            voice_id=voice_id,
            force=False,
            target_lang=target_lang,
        )
        
        # dubbing：强制走 SSOT（读取 artifacts/subtitles.json）
        class TaskAdapter:
            def __init__(self, t: dict, voice_override: str | None, target_lang: str):
                self.task_id = t.get("task_id") or t.get("id")  # 必须能拿到真实 task_id
                self.id = self.task_id  # 兼容某些 step 只读 .id
                self.tenant_id = t.get("tenant_id") or t.get("tenant") or "default"
                self.project_id = t.get("project_id") or t.get("project") or "default"
                self.target_lang = target_lang
                self.voice_id = voice_override or t.get("voice_id")
                self.dub_provider = t.get("dub_provider") or "edge-tts"

        task_adapter = TaskAdapter(task, voice_override=voice_id, target_lang=target_lang)
        asyncio.run(run_dub_step_ssot(task_adapter))
        audio_key = None
        if workspace.mm_audio_exists():
            audio_path = workspace.mm_audio_path
            audio_key = upload_task_artifact(task, audio_path, "mm_audio.mp3", task_id=task_id)
        _repo_upsert(
            repo,
            task_id,
            {
                **status_update,
                "last_step": current_step,
                "mm_audio_path": audio_key,
            },
        )

        current_step = "pack"
        _repo_upsert(repo, task_id, {**status_update, "last_step": current_step})
        pack_req = PackRequest(task_id=task_id)
        pack_res = asyncio.run(run_pack_step_v1(pack_req))
        pack_key = None
        if isinstance(pack_res, dict):
            pack_key = pack_res.get("pack_key") or pack_res.get("zip_key")
        _repo_upsert(
            repo,
            task_id,
            {
                "status": "done",
                "last_step": current_step,
                "pack_key": pack_key,
                "pack_type": "capcut_v18" if pack_key else None,
                "pack_status": "ready" if pack_key else None,
                "error_message": None,
                "error_reason": None,
            },
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Pipeline failed for task %s", task_id)
        _repo_upsert(
            repo,
            task_id,
            {
                "status": "failed",
                "last_step": current_step,
                "error_message": str(exc),
                "error_reason": "pipeline_failed",
            },
        )


@pages_router.get("/tasks/{task_id}", response_class=HTMLResponse)
async def task_workbench_page(
    request: Request, task_id: str, repo=Depends(get_task_repository)
) -> HTMLResponse:
    """Render the per-task workbench page."""

    task = repo.get(task_id)
    if not task:
        return templates.TemplateResponse(
            "task_not_found.html",
            {"request": request, "task_id": task_id},
            status_code=404,
        )

    app_settings = get_settings()
    env_summary = {
        "workspace_root": app_settings.workspace_root,
        "douyin_api_base": getattr(app_settings, "douyin_api_base", ""),
        "whisper_model": getattr(app_settings, "whisper_model", ""),
        "gpt_model": getattr(app_settings, "gpt_model", ""),
        "asr_backend": getattr(app_settings, "asr_backend", None) or "whisper",
        "subtitles_backend": getattr(app_settings, "subtitles_backend", "gemini"),
        "gemini_model": getattr(app_settings, "gemini_model", ""),
    }
    try:
        from gateway.app.providers.registry import resolve_tool_providers

        env_summary["defaults"] = resolve_tool_providers().get("tools", {})
    except Exception:
        env_summary["defaults"] = {}

    paths = _resolve_download_urls(task)
    detail = _task_to_detail(task)
    task_json = {
        "task_id": detail.task_id,
        "status": detail.status,
        "platform": detail.platform,
        "category_key": detail.category_key,
        "content_lang": detail.content_lang,
        "ui_lang": detail.ui_lang,
        "source_url": detail.source_url,
        "raw_path": detail.raw_path,
        "origin_srt_path": detail.origin_srt_path,
        "mm_srt_path": detail.mm_srt_path,
        "mm_audio_path": detail.mm_audio_path,
        "mm_txt_path": paths.get("mm_txt_path"),
        "pack_path": detail.pack_path,
        "scenes_path": detail.scenes_path,
        "scenes_status": detail.scenes_status,
        "scenes_key": detail.scenes_key,
        "scenes_error": detail.scenes_error,
        "subtitles_status": detail.subtitles_status,
        "subtitles_key": detail.subtitles_key,
        "subtitles_error": detail.subtitles_error,
        "publish_status": detail.publish_status,
        "publish_provider": detail.publish_provider,
        "publish_key": detail.publish_key,
        "publish_url": detail.publish_url,
        "published_at": detail.published_at,
    }
    task_view = {"source_url_open": _extract_first_http_url(task.get("source_url"))}

    return templates.TemplateResponse(
        "task_workbench.html",
        {
            "request": request,
            "task": detail,
            "task_json": task_json,
            "task_view": task_view,
            "env_summary": env_summary,
            "features": get_features(),
        },
    )


@api_router.post("/tasks", response_model=TaskDetail)
def create_task(
    payload: TaskCreate,
    background_tasks: BackgroundTasks,
    repo=Depends(get_task_repository),
):
    """Create a Task record and kick off the V1 pipeline asynchronously."""

    source_text = payload.source_url.strip()
    platform = payload.platform or _infer_platform_from_url(source_text)
    task_id = uuid4().hex[:12]

    task_payload = {
        "task_id": task_id,
        "title": payload.title,
        "source_url": source_text,
        "platform": platform,
        "account_id": payload.account_id,
        "account_name": payload.account_name,
        "video_type": payload.video_type,
        "template": payload.template,
        "category_key": payload.category_key or "beauty",
        "content_lang": payload.content_lang or "my",
        "ui_lang": payload.ui_lang or "en",
        "style_preset": payload.style_preset,
        "face_swap_enabled": bool(payload.face_swap_enabled),
        "status": "pending",
        "last_step": None,
        "error_message": None,
    }
    task_payload = normalize_task_payload(task_payload, is_new=True)
    repo.create(task_payload)
    backend = os.getenv("TASK_REPO_BACKEND", "").lower() or "file"
    logger.info(
        "created task_id=%s tenant=%s backend=%s",
        task_id,
        task_payload.get("tenant", "default"),
        backend,
    )
    stored_task = repo.get(task_id)
    if not stored_task:
        raise HTTPException(
            status_code=500,
            detail=f"Task persistence failed for task_id={task_id}",
        )

    background_tasks.add_task(_run_pipeline_background, task_id, repo)

    return _task_to_detail(stored_task)


@api_router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    account_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500, alias="limit"),
    repo=Depends(get_task_repository),
):
    """List tasks with optional filtering by account or status."""

    filters = {}
    if account_id:
        filters["account_id"] = account_id
    if status:
        filters["status"] = status

    items = sort_tasks_by_created(repo.list(filters=filters))
    total = len(items)
    items = items[(page - 1) * page_size : (page - 1) * page_size + page_size]

    summaries: list[TaskSummary] = []
    for t in items:
        download_paths = _resolve_download_urls(t)
        pack_path = download_paths.get("pack_path")
        scenes_path = download_paths.get("scenes_path")
        status = t.get("status") or "pending"
        if status != "error" and pack_path:
            status = "ready"
        summaries.append(
            TaskSummary(
                task_id=str(t.get("task_id") or t.get("id")),
                title=t.get("title"),
                source_url=str(t.get("source_url")) if t.get("source_url") else None,
                source_link_url=_extract_first_http_url(t.get("source_url")),
                platform=t.get("platform"),
                account_id=t.get("account_id"),
                account_name=t.get("account_name"),
                video_type=t.get("video_type"),
                template=t.get("template"),
                category_key=t.get("category_key") or "beauty",
                content_lang=t.get("content_lang") or "my",
                ui_lang=t.get("ui_lang") or "en",
                style_preset=t.get("style_preset"),
                face_swap_enabled=bool(t.get("face_swap_enabled")),
                status=status,
                last_step=t.get("last_step"),
                duration_sec=t.get("duration_sec"),
                thumb_url=t.get("thumb_url"),
                pack_path=pack_path,
                scenes_path=scenes_path,
                scenes_status=t.get("scenes_status"),
                scenes_key=t.get("scenes_key"),
                scenes_error=t.get("scenes_error"),
                subtitles_status=t.get("subtitles_status"),
                subtitles_key=t.get("subtitles_key"),
                subtitles_error=t.get("subtitles_error"),
                created_at=(coerce_datetime(t.get("created_at") or t.get("created") or t.get("createdAt")) or datetime(1970, 1, 1, tzinfo=timezone.utc)),
                updated_at=coerce_datetime(t.get("updated_at") or t.get("updatedAt")),
                error_message=t.get("error_message"),
                error_reason=t.get("error_reason"),
                parse_provider=t.get("parse_provider"),
                subtitles_provider=t.get("subtitles_provider"),
                dub_provider=t.get("dub_provider"),
                pack_provider=t.get("pack_provider"),
                face_swap_provider=t.get("face_swap_provider"),
                publish_status=t.get("publish_status"),
                publish_provider=t.get("publish_provider"),
                publish_key=t.get("publish_key"),
                publish_url=t.get("publish_url"),
                published_at=t.get("published_at"),
                priority=t.get("priority"),
                assignee=t.get("assignee"),
                ops_notes=t.get("ops_notes"),
            )
        )

    return TaskListResponse(items=summaries, page=page, page_size=page_size, total=total)


@api_router.get("/tasks/{task_id}/text", response_class=PlainTextResponse)
def get_task_text(
    task_id: str,
    kind: str = Query(default=..., pattern="^(origin_srt|mm_txt|mm_srt|mm_edited)$"),
    repo=Depends(get_task_repository),
):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")

    if kind == "mm_edited":
        path = _mm_edited_path(task_id)
        if not path.exists():
            return PlainTextResponse(
                "",
                status_code=200,
                headers={"X-Text-Exists": "0"},
            )
        return PlainTextResponse(
            path.read_text(encoding="utf-8"),
            status_code=200,
            headers={"X-Text-Exists": "1"},
        )

    path = _resolve_text_path(task_id, kind)
    if not path:
        raise HTTPException(status_code=404, detail=f"{kind} not found")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(errors="ignore")


@api_router.post("/tasks/{task_id}/mm_edited")
def save_mm_edited(task_id: str, payload: EditedTextRequest):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")
    path = _mm_edited_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(text + "\n", encoding="utf-8")
        return JSONResponse(
            {
                "ok": True,
                "task_id": task_id,
                "kind": "mm_edited",
                "bytes": len(text.encode("utf-8")),
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"write mm_edited failed: {exc}") from exc




@api_router.get("/tasks/{task_id}", response_model=TaskDetail)
def get_task(task_id: str, repo=Depends(get_task_repository)):
    """Retrieve a single task by id."""

    t = repo.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")

    return _task_to_detail(t)


@api_router.post("/tasks/{task_id}/parse")
def build_parse(
    task_id: str,
    payload: ParseTaskRequest | None = None,
    repo=Depends(get_task_repository),
):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    link = task.get("source_url") or task.get("link")
    if not link:
        raise HTTPException(status_code=400, detail="source_url is empty; cannot parse")

    platform = (payload.platform if payload else None) or task.get("platform")
    repo.upsert(task_id, {"status": "processing", "last_step": "parse"})
    parse_req = ParseRequest(task_id=task_id, platform=platform, link=link)

    try:
        parse_res = asyncio.run(run_parse_step_v1(parse_req))
    except HTTPException as exc:
        repo.upsert(
            task_id,
            {
                "status": "failed",
                "last_step": "parse",
                "error_message": str(exc.detail),
                "error_reason": "parse_failed",
            },
        )
        raise

    raw_file = raw_path(task_id)
    raw_key = None
    if raw_file.exists():
        raw_key = upload_task_artifact(task, raw_file, "raw.mp4", task_id=task_id)
    duration_sec = parse_res.get("duration_sec") if isinstance(parse_res, dict) else None
    repo.upsert(
        task_id,
        {
            "status": "processing",
            "last_step": "parse",
            "raw_path": raw_key,
            "duration_sec": duration_sec,
            "error_message": None,
            "error_reason": None,
        },
    )

    stored = repo.get(task_id)
    return _task_to_detail(stored)


async def _run_subtitles_job(
    *,
    task_id: str,
    target_lang: str,
    force: bool,
    translate: bool,
    repo,
) -> None:
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    repo.upsert(
        task_id,
        {
            "status": "processing",
            "last_step": "subtitles",
            "subtitles_status": "running",
            "subtitles_error": None,
        },
    )
    subs_req = SubtitlesRequest(
        task_id=task_id,
        target_lang=target_lang,
        force=force,
        translate=translate,
        with_scenes=True,
    )
    await run_subtitles_step_v1(subs_req)

    workspace = Workspace(task_id)
    origin_key = (
        upload_task_artifact(task, workspace.origin_srt_path, "origin.srt", task_id=task_id)
        if workspace.origin_srt_path.exists()
        else None
    )
    mm_key = (
        upload_task_artifact(task, workspace.mm_srt_path, "mm.srt", task_id=task_id)
        if workspace.mm_srt_path.exists()
        else None
    )
    mm_txt_path = workspace.mm_srt_path.with_suffix(".txt")
    if mm_txt_path.exists():
        upload_task_artifact(task, mm_txt_path, "mm.txt", task_id=task_id)

    subtitles_dir = Path("deliver") / "subtitles" / task_id
    subtitles_key = str(subtitles_dir / "subtitles.json")

    repo.upsert(
        task_id,
        {
            "origin_srt_path": origin_key,
            "mm_srt_path": mm_key,
            "last_step": "subtitles",
            "subtitles_status": "ready",
            "subtitles_key": subtitles_key,
            "subtitle_structure_path": subtitles_key,
            "subtitles_error": None,
        },
    )


async def _run_subtitles_background(
    task_id: str,
    target_lang: str,
    force: bool,
    translate: bool,
    repo,
) -> None:
    try:
        await _run_subtitles_job(
            task_id=task_id,
            target_lang=target_lang,
            force=force,
            translate=translate,
            repo=repo,
        )
    except HTTPException as exc:
        repo.upsert(
            task_id,
            {
                "subtitles_status": "error",
                "subtitles_error": f"{exc.status_code}: {exc.detail}",
            },
        )
        logger.exception(
            "SUB2_FAIL",
            extra={"task_id": task_id, "step": "subtitles", "phase": "exception"},
        )
    except Exception as exc:
        repo.upsert(task_id, {"subtitles_status": "error", "subtitles_error": str(exc)})
        logger.exception(
            "SUB2_FAIL",
            extra={"task_id": task_id, "step": "subtitles", "phase": "exception"},
        )


async def _run_dub_job(task_id: str, payload: DubProviderRequest, repo: ITaskRepository) -> None:
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    provider = (payload.provider or "edge-tts").lower()
    if provider == "edge":
        provider = "edge-tts"
    if provider not in {"edge-tts", "lovo"}:
        raise HTTPException(status_code=400, detail="Unsupported dub provider")

    settings = get_settings()
    if provider == "lovo" and not getattr(settings, "lovo_api_key", None):
        raise HTTPException(status_code=400, detail="LOVO_API_KEY is not configured")

    repo.upsert(
        task_id,
        {
            "status": "processing",
            "last_step": "dub",
            "dub_status": "running",
            "dub_error": None,
        },
    )

    try:
        class TaskAdapter:
            def __init__(self, t: dict, voice_override: str | None, provider: str):
                self.task_id = t.get("task_id") or t.get("id")
                self.id = self.task_id
                self.tenant_id = t.get("tenant_id") or t.get("tenant") or "default"
                self.project_id = t.get("project_id") or t.get("project") or "default"
                self.target_lang = t.get("target_lang") or t.get("content_lang") or "my"
                self.voice_id = voice_override or t.get("voice_id")
                self.dub_provider = provider

        task_adapter = TaskAdapter(task, voice_override=payload.voice_id, provider=provider)

        # 核心：SSOT dubbing
        await run_dub_step_ssot(task_adapter)

        from gateway.app.utils.keys import KeyBuilder

        audio_key = KeyBuilder.build(
            task_adapter.tenant_id,
            task_adapter.project_id,
            task_adapter.task_id,
            "artifacts/voice/full.mp3",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Dubbing step failed for task_id=%s", task_id)
        raise HTTPException(status_code=500, detail=f"Dubbing step failed: {exc}")

    repo.upsert(
        task_id,
        {
            "mm_audio_path": audio_key,
            "dub_provider": provider,
            "last_step": "dubbing",
            "dub_status": "ready",
            "dub_error": None,
        },
    )


async def _run_dub_background(task_id: str, payload: DubProviderRequest, repo: ITaskRepository) -> None:
    try:
        await _run_dub_job(task_id, payload, repo)
    except HTTPException as exc:
        repo.upsert(
            task_id,
            {"dub_status": "error", "dub_error": f"{exc.status_code}: {exc.detail}"},
        )
        logger.exception("DUB3_FAIL", extra={"task_id": task_id, "step": "dub", "phase": "exception"})
    except Exception as exc:
        repo.upsert(task_id, {"dub_status": "error", "dub_error": str(exc)})
        logger.exception("DUB3_FAIL", extra={"task_id": task_id, "step": "dub", "phase": "exception"})


async def _run_pack_job(task_id: str, repo) -> None:
    repo.upsert(
        task_id,
        {
            "status": "processing",
            "last_step": "pack",
            "pack_status": "running",
            "pack_error": None,
        },
    )
    pack_req = PackRequest(task_id=task_id)
    pack_res = await run_pack_step_v1(pack_req)
    pack_key = None
    if isinstance(pack_res, dict):
        pack_key = pack_res.get("pack_key") or pack_res.get("zip_key")
    repo.upsert(
        task_id,
        {
            "status": "ready",
            "last_step": "pack",
            "pack_key": pack_key,
            "pack_type": "capcut_v18" if pack_key else None,
            "pack_status": "ready" if pack_key else None,
            "pack_error": None,
        },
    )


async def _run_pack_background(task_id: str, repo) -> None:
    try:
        await _run_pack_job(task_id, repo)
    except HTTPException as exc:
        repo.upsert(
            task_id,
            {
                "pack_status": "error",
                "pack_error": f"{exc.status_code}: {exc.detail}",
            },
        )
        logger.exception("PACK_FAIL", extra={"task_id": task_id, "step": "pack", "phase": "exception"})
    except Exception as exc:
        repo.upsert(task_id, {"pack_status": "error", "pack_error": str(exc)})
        logger.exception("PACK_FAIL", extra={"task_id": task_id, "step": "pack", "phase": "exception"})


@api_router.post("/tasks/{task_id}/scenes")
def build_scenes(
    task_id: str,
    background_tasks: BackgroundTasks,
    payload: ScenesRequest | None = None,
    repo=Depends(get_task_repository),
):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.get("scenes_status") in {"queued", "running"}:
        return {"status": "already_running", "task_id": task_id, "step": "scenes"}

    def _update(task_id: str, fields: dict) -> None:
        repo.upsert(task_id, fields)

    repo.upsert(
        task_id,
        {
            "status": "processing",
            "last_step": "scenes",
            "scenes_status": "queued",
            "scenes_error": None,
        },
    )

    enqueue_scenes_build(
        task_id,
        task=task,
        object_exists=object_exists,
        update_task=_update,
        background_tasks=background_tasks,
    )
    return {"status": "queued", "task_id": task_id, "step": "scenes"}

@api_router.post("/tasks/{task_id}/pack")
async def build_pack(
    task_id: str,
    repo=Depends(get_task_repository),
):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.get("pack_status") in {"queued", "running"}:
        return {"status": "already_running", "task_id": task_id, "step": "pack"}

    repo.upsert(
        task_id,
        {
            "status": "processing",
            "last_step": "pack",
            "pack_status": "queued",
            "pack_error": None,
        },
    )
    asyncio.create_task(_run_pack_background(task_id, repo))
    return {"status": "queued", "task_id": task_id, "step": "pack"}

@api_router.post("/tasks/{task_id}/dub")
async def rerun_dub(
    task_id: str,
    payload: DubProviderRequest,
    repo: ITaskRepository = Depends(get_task_repository),
):
    """Re-run dubbing for a task (SSOT: reads artifacts/subtitles.json)."""

    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.get("dub_status") in {"queued", "running"}:
        return {"status": "already_running", "task_id": task_id, "step": "dub"}

    provider = (payload.provider or "edge-tts").lower()
    if provider == "edge":
        provider = "edge-tts"
    if provider not in {"edge-tts", "lovo"}:
        raise HTTPException(status_code=400, detail="Unsupported dub provider")

    settings = get_settings()
    if provider == "lovo" and not getattr(settings, "lovo_api_key", None):
        raise HTTPException(status_code=400, detail="LOVO_API_KEY is not configured")

    repo.upsert(
        task_id,
        {
            "status": "processing",
            "last_step": "dub",
            "dub_status": "queued",
            "dub_error": None,
        },
    )
    asyncio.create_task(_run_dub_background(task_id, payload, repo))
    return {"status": "queued", "task_id": task_id, "step": "dub"}


@api_router.post("/tasks/{task_id}/publish")
def publish_task(
    task_id: str,
    payload: PublishTaskRequest | None = None,
    repo=Depends(get_task_repository),
):
    db = SessionLocal()
    try:
        res = publish_task_pack(
            task_id,
            db,
            provider=(payload.provider if payload else None),
            force=(payload.force if payload else False),
        )
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if task:
            repo.upsert(
                task_id,
                {
                    "publish_provider": task.publish_provider,
                    "publish_key": task.publish_key,
                    "publish_url": task.publish_url,
                    "publish_status": task.publish_status,
                    "published_at": task.published_at,
                },
            )
        download_url = res.get("download_url") or (resolve_download_url(task) if task else "")
        return {
            "task_id": task_id,
            "provider": res.get("provider"),
            "publish_key": res.get("publish_key"),
            "download_url": download_url,
            "published_at": res.get("published_at"),
        }
    finally:
        db.close()


@api_router.post("/tasks/{task_id}/subtitles")
async def build_subtitles(
    task_id: str,
    payload: SubtitlesTaskRequest | None = None,
    repo=Depends(get_task_repository),
):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.get("subtitles_status") in {"queued", "running"}:
        return {"status": "already_running", "task_id": task_id, "step": "subtitles"}

    target_lang = (payload.target_lang if payload else None) or task.get("content_lang") or "my"
    force = payload.force if payload else False
    translate = payload.translate if payload else True

    repo.upsert(
        task_id,
        {
            "status": "processing",
            "last_step": "subtitles",
            "subtitles_status": "queued",
            "subtitles_error": None,
        },
    )
    asyncio.create_task(_run_subtitles_background(task_id, target_lang, force, translate, repo))
    return {"status": "queued", "task_id": task_id, "step": "subtitles"}



@api_router.delete("/tasks/{task_id}")
def delete_task(
    task_id: str,
    delete_assets: bool = Query(default=False),
    repo=Depends(get_task_repository),
):
    """Delete a task record and optionally purge stored artifacts."""

    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if delete_assets:
        try:
            purged = purge_task_artifacts(task)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Asset purge failed: {exc}") from exc
    else:
        purged = 0

    try:
        delete_task_record(task)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Delete failed: {exc}") from exc

    return {"ok": True, "task_id": task_id, "deleted_assets": bool(delete_assets), "purged": purged}


router = api_router

__all__ = ["api_router", "pages_router", "router"]
