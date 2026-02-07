"""Task API and HTML routers for the gateway application."""

import asyncio
import json
import hashlib
import hmac
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, Security, UploadFile
from fastapi.security.api_key import APIKeyHeader
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from pydantic import BaseModel

from ..config import get_settings
from ..core.features import get_features
from ..schemas import (
    DubRequest,
    DubResponse,
    PackRequest,
    ParseRequest,
    SubtitlesRequest,
    TaskCreate,
    TaskDetail,
    TaskListResponse,
    TaskSummary,
    TaskUpdate,
)

from gateway.app.web.templates import render_template
from gateway.app.services.workbench_registry import resolve_workbench_spec
from gateway.app.deps import get_task_repository
from gateway.app.ports.storage_provider import get_storage_service  # 只保留这一处依赖注入入口

# Ports / typing
from gateway.ports.repository import ITaskRepository  # 如路径不对，按你们 ports 实际文件修

# Canonical SSOT dubbing step (v1.62+)
from gateway.app.steps.dubbing import run_dub_step as run_dub_step_ssot

# Legacy v1 pipeline steps (parse/subtitles/pack). Dubbing 保留 v1 名称但必须显式别名，避免覆盖 SSOT
from ..services.steps_v1 import (
    compute_subtitles_params,
    run_pack_step as run_pack_step_v1,
    run_parse_step as run_parse_step_v1,
    run_subtitles_step as run_subtitles_step_v1,
    run_subtitles_step_entry,
    run_dub_step as run_dub_step_v1,
)
from gateway.app.services.status_policy.utils import policy_upsert


def _policy_upsert(repo, task_id: str, updates: dict, *, task: dict | None = None, step: str = "router.tasks", force: bool = False):
    return policy_upsert(repo, task_id, task, updates, step=step, force=force)
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
from gateway.app.ports.storage_provider import get_storage_service
from gateway.app.services.scene_split import enqueue_scenes_build
from gateway.app.services.publish_service import publish_task_pack, resolve_download_url
from gateway.app.db import SessionLocal

from gateway.app.task_repo_utils import normalize_task_payload, sort_tasks_by_created
from gateway.app.services.task_cleanup import delete_task_record, purge_task_artifacts
from gateway.app.utils.pipeline_config import parse_pipeline_config, pipeline_config_to_storage
from gateway.app.utils.subtitle_probe import probe_subtitles

from ..core.workspace import (
    Workspace,
    origin_srt_path,
    deliver_pack_zip_path,
    raw_path,
    relative_to_workspace,
    task_base_dir,
)

logger = logging.getLogger(__name__)

AUDIO_MM_KEY_TEMPLATE = "deliver/tasks/{task_id}/audio_mm.mp3"
OP_HEADER_KEY = "X-OP-KEY"


class DubProviderRequest(BaseModel):
    provider: str | None = None
    voice_id: str | None = None
    mm_text: str | None = None


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
api_key_header = APIKeyHeader(name=OP_HEADER_KEY, auto_error=False)
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
    kind: str | None = Query(default=None),
    repo=Depends(get_task_repository),
):
    """Render the task board HTML page."""

    db_tasks = sort_tasks_by_created(repo.list())
    kind_norm = (kind or "").strip().lower()
    if kind_norm == "apollo_avatar":
        db_tasks = [
            t
            for t in db_tasks
            if (str(t.get("platform") or "").lower() == "apollo_avatar")
            or (str(t.get("category_key") or "").lower() == "apollo_avatar")
        ]

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
                "selected_tool_ids": _normalize_selected_tool_ids(t.get("selected_tool_ids")),
            }
        )

    return render_template(
        request=request,
        name="tasks.html",
        ctx={
            "tasks": rows,
            "features": get_features(),
            "tasks_kind": kind_norm or "tasks",
        },
    )


@pages_router.get("/tasks/new", response_class=HTMLResponse)
async def tasks_new(request: Request) -> HTMLResponse:
    """Render suitcase quick-create page."""

    return render_template(
        request=request,
        name="tasks_new.html",
        ctx={"features": get_features()},
    )


@pages_router.get("/tasks/apollo-avatar/new", response_class=HTMLResponse)
async def tasks_apollo_avatar_new(request: Request) -> HTMLResponse:
    settings = get_settings()
    if not bool(getattr(settings, "enable_apollo_avatar", False)):
        raise HTTPException(status_code=404, detail="ApolloAvatar is disabled")
    return render_template(
        request=request,
        name="tasks_apollo_avatar_new.html",
        ctx={
            "apollo_avatar_live_enabled": bool(
                getattr(settings, "apollo_avatar_live_enabled", False)
            ),
            "demo_asset_base_url": getattr(settings, "demo_asset_base_url", "") or "",
        },
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
    return render_template(
        request=request,
        name="pipeline_lab.html",
        ctx={"env_summary": env_summary},
    )


@pages_router.get("/tools/hub", response_class=HTMLResponse)
async def tools_hub_page(request: Request) -> HTMLResponse:
    """Render tools hub list page."""

    return render_template(
        request=request,
        name="tools_hub.html",
        ctx={},
    )


@pages_router.get("/tools/{tool_id}", response_class=HTMLResponse)
async def tool_detail_page(request: Request, tool_id: str) -> HTMLResponse:
    """Render tool detail page."""

    return render_template(
        request=request,
        name="tool_detail.html",
        ctx={"tool_id": tool_id},
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
    key = _task_key(task, "mm_srt_path")
    if not key or not object_exists(key):
        return _not_ready_response(task, "subs_mm", ["mm_srt_path"])
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
    mm_key = _task_key(task, "mm_srt_path")
    if not mm_key or not object_exists(mm_key):
        return _not_ready_response(task, "mm_txt", ["mm_srt_path"])
    txt_key = mm_key[:-4] + ".txt" if mm_key.endswith(".srt") else f"{mm_key}.txt"
    if not object_exists(txt_key):
        return _not_ready_response(task, "mm_txt", ["mm_txt_path"])
    return _text_or_redirect(txt_key, inline=inline)


@pages_router.get("/v1/tasks/{task_id}/audio_mm")
def download_audio_mm(task_id: str, repo=Depends(get_task_repository)):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="dubbed audio not found")
    key = _task_value(task, "mm_audio_key")
    if not key or not object_exists(str(key)):
        return _not_ready_response(task, "audio_mm", ["mm_audio_key"])
    logger.info("audio_mm download: task_id=%s key=%s", task_id, key)
    return RedirectResponse(url=get_download_url(str(key)), status_code=302)


@pages_router.get("/v1/tasks/{task_id}/pack")
def download_pack(task_id: str, repo=Depends(get_task_repository)):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Pack not found")
    pack_type = _task_value(task, "pack_type")
    if pack_type == "capcut_v18":
        pack_key = _task_value(task, "pack_key") or _task_value(task, "pack_path")
        if not pack_key or not object_exists(str(pack_key)):
            return _not_ready_response(task, "pack", ["pack_key"])
        return RedirectResponse(url=get_download_url(str(pack_key)), status_code=302)

    key = _task_value(task, "pack_key") or _task_value(task, "pack_path")
    if not key or not object_exists(str(key)):
        return _not_ready_response(task, "pack", ["pack_key"])
    return RedirectResponse(url=get_download_url(str(key)), status_code=302)


@pages_router.get("/v1/tasks/{task_id}/scenes")
def download_scenes(task_id: str, repo=Depends(get_task_repository)):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Scenes not found")
    scenes_key = _task_value(task, "scenes_key")
    scenes_status = str(_task_value(task, "scenes_status") or "").lower()
    if scenes_status == "skipped":
        return _not_ready_response(task, "scenes", ["scenes_skipped"], reason="not_applicable")
    if scenes_status == "failed":
        return _not_ready_response(task, "scenes", ["scenes_failed"], reason="failed")
    if not scenes_key or not object_exists(str(scenes_key)):
        return _not_ready_response(task, "scenes", ["scenes_key"])
    return RedirectResponse(url=get_download_url(str(scenes_key)), status_code=302)


@pages_router.get("/v1/tasks/{task_id}/publish_bundle")
def download_publish_bundle(task_id: str, repo=Depends(get_task_repository)):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    tmpdir = tempfile.TemporaryDirectory()
    storage = get_storage_service()

    def _download_if_exists(key: str | None, dest: Path) -> bool:
        if not key or not object_exists(str(key)):
            return False
        try:
            storage.download_file(str(key), str(dest))
            return dest.exists()
        except Exception:
            return False

    pack_key = _task_value(task, "pack_key") or _task_value(task, "pack_path")
    scenes_key = _task_value(task, "scenes_key")
    missing = []
    if not pack_key or not object_exists(str(pack_key)):
        missing.append("pack_key")
    if str(_task_value(task, "scenes_status") or "").lower() != "skipped":
        if not scenes_key or not object_exists(str(scenes_key)):
            missing.append("scenes_key")
    if missing:
        return _not_ready_response(task, "publish_bundle", missing)
    pack_local = Path(tmpdir.name) / "pack.zip"
    scenes_local = Path(tmpdir.name) / "scenes.zip"

    _download_if_exists(str(pack_key) if pack_key else None, pack_local)
    _download_if_exists(str(scenes_key) if scenes_key else None, scenes_local)

    bundle = _build_copy_bundle(task)
    zip_path = Path(tmpdir.name) / f"publish_bundle_{task_id}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if pack_local.exists():
            zf.write(pack_local, arcname="pack.zip")
        if scenes_local.exists():
            zf.write(scenes_local, arcname="scenes.zip")
        zf.writestr("copy/caption.txt", bundle.get("caption", ""))
        zf.writestr("copy/hashtags.txt", bundle.get("hashtags", ""))
        zf.writestr("copy/comment_cta.txt", bundle.get("comment_cta", ""))
        zf.writestr("copy/link_text.txt", bundle.get("link_text", ""))
        zf.writestr(
            "copy/publish_time_suggestion.txt",
            bundle.get("publish_time_suggestion", ""),
        )
        zf.writestr("SOP.md", _publish_sop_markdown())
        zf.writestr(
            "README.md",
            "This is the edit bundle. Final publish bundle will be available in v2.0.\n",
        )

    def iterfile():
        with zip_path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                yield chunk
        tmpdir.cleanup()

    headers = {
        "Content-Disposition": f"attachment; filename=publish_bundle_{task_id}.zip"
    }
    return StreamingResponse(iterfile(), media_type="application/zip", headers=headers)


@pages_router.get("/v1/tasks/{task_id}/publish_hub")
def v1_task_publish_hub(task_id: str, repo=Depends(get_task_repository)):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _publish_hub_payload(task)


@pages_router.get("/v1/tasks/{task_id}/status")
def task_status(task_id: str, repo=Depends(get_task_repository)):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    raw_key = _task_key(task, "raw_path")
    origin_key = _task_key(task, "origin_srt_path")
    mm_key = _task_key(task, "mm_srt_path")
    mm_txt_key = None
    if mm_key and mm_key.endswith(".srt"):
        mm_txt_key = f"{mm_key[:-4]}.txt"
    audio_key = _task_key(task, "mm_audio_key") or _task_key(task, "mm_audio_path")
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
    if kind == "publish_bundle":
        return f"/v1/tasks/{safe_id}/publish_bundle"
    return None


def _get_op_access_key() -> Optional[str]:
    key = (os.getenv("OP_ACCESS_KEY") or "").strip()
    return key or None


def _op_gate_enabled() -> bool:
    return bool(_get_op_access_key())


def _op_key_valid(request: Request) -> bool:
    secret = _get_op_access_key()
    if not secret:
        return True
    header_val = (request.headers.get(OP_HEADER_KEY) or "").strip()
    return hmac.compare_digest(header_val, secret)

def _op_key_valid_value(op_key: str | None) -> bool:
    secret = _get_op_access_key()
    if not secret:
        return True
    if not op_key:
        return False
    return hmac.compare_digest(op_key, secret)


def _require_op_key(request: Request) -> None:
    if not _op_key_valid(request):
        raise HTTPException(status_code=401, detail="OP key required")


def _op_sign(task_id: str, kind: str, exp: int) -> str:
    secret = _get_op_access_key()
    if not secret:
        return ""
    msg = f"{task_id}:{kind}:{exp}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def _op_verify(task_id: str, kind: str, exp: int, sig: str) -> bool:
    secret = _get_op_access_key()
    if not secret:
        return True
    if not sig:
        return False
    expected = _op_sign(task_id, kind, exp)
    return hmac.compare_digest(expected, sig)


def _download_code(task_id: str) -> str:
    return str(task_id).upper()[:6]


def _signed_op_url(task_id: str, kind: str) -> str:
    exp = int(time.time()) + 86400
    sig = _op_sign(task_id, kind, exp)
    base = f"/op/dl/{task_id}?kind={kind}&exp={exp}"
    return f"{base}&sig={sig}" if sig else base


def _read_mm_txt_from_task(task: dict) -> str:
    mm_key = _task_key(task, "mm_srt_path")
    if not mm_key:
        return ""
    txt_key = mm_key[:-4] + ".txt" if mm_key.endswith(".srt") else f"{mm_key}.txt"
    if not object_exists(txt_key):
        return ""
    data = get_object_bytes(txt_key)
    if not data:
        return ""
    try:
        return data.decode("utf-8").strip()
    except UnicodeDecodeError:
        return data.decode(errors="ignore").strip()


def _publish_sop_markdown() -> str:
    return (
        "# Publish SOP\n"
        "1) Download the edit bundle (pack.zip).\n"
        "2) Import into CapCut and finish edits.\n"
        "3) Copy caption and hashtags from Copy Bundle.\n"
        "4) Publish manually (publish bundle in v2.0).\n"
    )


def _build_copy_bundle(task: dict) -> dict[str, str]:
    caption = _read_mm_txt_from_task(task) or (task.get("title") or "")
    return {
        "caption": caption.strip(),
        "hashtags": "",
        "comment_cta": "",
        "link_text": task.get("publish_url") or "",
        "publish_time_suggestion": "",
    }


def _deliverable_url(task_id: str, task: dict, kind: str) -> Optional[str]:
    if kind == "final_mp4":
        key = _task_key(task, "raw_path")
        return _signed_op_url(task_id, "raw") if key and object_exists(key) else None
    if kind == "pack_zip":
        pack_type = _task_value(task, "pack_type")
        pack_key = _task_value(task, "pack_key") or _task_value(task, "pack_path")
        if pack_type == "capcut_v18" and pack_key and object_exists(str(pack_key)):
            return _signed_op_url(task_id, "pack")
        if pack_key and object_exists(str(pack_key)):
            return _signed_op_url(task_id, "pack")
        return None
    if kind == "scenes_zip":
        scenes_key = _task_value(task, "scenes_key")
        scenes_path = _task_value(task, "scenes_path")
        scenes_status = str(_task_value(task, "scenes_status") or "").lower()
        if scenes_key and object_exists(str(scenes_key)):
            return _signed_op_url(task_id, "scenes")
        if scenes_path and scenes_status == "ready":
            return _signed_op_url(task_id, "scenes")
        return None
    if kind == "origin_srt":
        key = _task_key(task, "origin_srt_path")
        return _signed_op_url(task_id, "origin_srt") if key and object_exists(key) else None
    if kind == "mm_srt":
        key = _task_key(task, "mm_srt_path")
        return _signed_op_url(task_id, "mm_srt") if key and object_exists(key) else None
    if kind == "mm_txt":
        mm_key = _task_key(task, "mm_srt_path")
        if not mm_key:
            return None
        txt_key = mm_key[:-4] + ".txt" if mm_key.endswith(".srt") else f"{mm_key}.txt"
        return _signed_op_url(task_id, "mm_txt") if object_exists(txt_key) else None
    if kind == "mm_audio":
        key = _task_key(task, "mm_audio_key") or _task_key(task, "mm_audio_path")
        return _signed_op_url(task_id, "mm_audio") if key and object_exists(key) else None
    if kind == "edit_bundle_zip":
        return _signed_op_url(task_id, "publish_bundle")
    return None


def _publish_hub_payload(task: dict) -> dict[str, object]:
    task_id = str(_task_value(task, "task_id") or _task_value(task, "id") or "")
    deliverables = {}
    for key, label in (
        ("pack_zip", "pack.zip"),
        ("scenes_zip", "scenes.zip"),
        ("origin_srt", "origin.srt"),
        ("mm_srt", "mm.srt"),
        ("mm_txt", "mm.txt"),
        ("mm_audio", "mm_audio"),
        ("edit_bundle_zip", "edit_bundle.zip"),
    ):
        url = _deliverable_url(task_id, task, key)
        if url:
            deliverables[key] = {"label": label, "url": url}
    short_code = _download_code(task_id)
    short_url = f"/d/{short_code}"

    return {
        "task_id": task_id,
        "gate_enabled": _op_gate_enabled(),
        "deliverables": deliverables,
        "copy_bundle": _build_copy_bundle(task),
        "download_code": short_code,
        "mobile": {
            "qr_target": short_url,
            "short_link": short_url,
            "short_url": short_url,
            "qr_url": short_url,
        },
        "sop_markdown": _publish_sop_markdown(),
        "archive": {
            "publish_provider": task.get("publish_provider") or "-",
            "publish_key": task.get("publish_key") or "-",
            "publish_status": task.get("publish_status") or "-",
            "publish_url": task.get("publish_url") or "-",
            "published_at": task.get("published_at") or "-",
        },
    }


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


def _not_ready_response(task: dict, artifact: str, missing: list[str], *, reason: str = "not_ready") -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "ok": False,
            "reason": reason,
            "task_id": str(_task_value(task, "task_id") or _task_value(task, "id") or ""),
            "artifact": artifact,
            "missing": missing,
            "status": {
                "subtitles": _task_value(task, "subtitles_status"),
                "dub": _task_value(task, "dub_status"),
                "scenes": _task_value(task, "scenes_status"),
                "pack": _task_value(task, "pack_status"),
                "publish": _task_value(task, "publish_status"),
            },
            "hint": "Call generate or wait for pipeline to finish.",
        },
    )


def _text_or_redirect(key: str, inline: bool) -> Response:
    if inline:
        data = get_object_bytes(key)
        if data is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return Response(content=data, media_type="text/plain; charset=utf-8")
    return RedirectResponse(url=get_download_url(key), status_code=302)


def _ensure_mp3_audio(src_path: Path, dst_path: Path) -> Path:
    if src_path.suffix.lower() == ".mp3":
        return src_path

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise HTTPException(status_code=500, detail="ffmpeg not found for mp3 conversion")

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src_path),
        "-codec:a",
        "libmp3lame",
        str(dst_path),
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0 or not dst_path.exists() or dst_path.stat().st_size == 0:
        raise HTTPException(
            status_code=500,
            detail=f"ffmpeg mp3 conversion failed: {p.stderr[-800:]}",
        )
    return dst_path


def _subtitle_cache_path(task_id: str) -> Path:
    return task_base_dir(task_id) / "subtitle_streams.json"


def _detect_subtitle_streams(raw_file: Path) -> dict[str, Any]:
    if not raw_file.exists():
        return {"status": "unknown", "reason": "raw_missing"}

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"status": "unknown", "reason": "ffprobe_missing"}

    cmd = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        str(raw_file),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        return {"status": "unknown", "reason": "ffprobe_failed"}

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"status": "unknown", "reason": "ffprobe_bad_json"}

    streams = payload.get("streams", []) or []
    subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]
    minimal_streams = [
        {
            "index": s.get("index"),
            "codec_name": s.get("codec_name"),
            "codec_type": s.get("codec_type"),
            "tags": s.get("tags") or {},
        }
        for s in subtitle_streams
    ]
    return {
        "status": "ok",
        "has_subtitle_stream": bool(subtitle_streams),
        "subtitle_streams": minimal_streams,
    }


def _get_subtitle_detection(task_id: str) -> dict[str, Any]:
    cache_path = _subtitle_cache_path(task_id)
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    raw_file = raw_path(task_id)
    result = _detect_subtitle_streams(raw_file)
    try:
        cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return result


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
        if task.get("mm_audio_key") or task.get("mm_audio_path")
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


def _normalize_selected_tool_ids(value: Any) -> Optional[list[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            decoded = json.loads(text)
        except Exception:
            decoded = None
        if isinstance(decoded, list):
            return [str(v) for v in decoded if str(v).strip()]
        return [v.strip() for v in text.split(",") if v.strip()]
    return None

def _task_to_detail(task: dict) -> TaskDetail:
    paths = _resolve_download_urls(task)
    status = task.get("status") or "pending"
    if status != "error" and paths.get("pack_path"):
        status = "ready"
    pipeline_config = parse_pipeline_config(task.get("pipeline_config"))

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
        "mm_audio_key": task.get("mm_audio_key"),
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
        "selected_tool_ids": _normalize_selected_tool_ids(task.get("selected_tool_ids")),
        "pipeline_config": pipeline_config,
        "no_dub": pipeline_config.get("no_dub") == "true",
        "dub_skip_reason": pipeline_config.get("dub_skip_reason"),
        "subtitle_track_kind": pipeline_config.get("subtitle_track_kind"),
    }

    allowed = _model_allowed_fields(TaskDetail)
    payload = {k: v for k, v in payload.items() if k in allowed}
    return TaskDetail(**payload)


def _extract_first_http_url(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"https?://\S+", text)
    return match.group(0) if match else None


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _repo_upsert(repo, task_id: str, patch: dict) -> None:
    _policy_upsert(repo, task_id, patch)


def _merge_probe_into_pipeline_config(
    pipeline_config: dict[str, str], probe: dict[str, Any] | None
) -> dict[str, str]:
    if not probe:
        return pipeline_config
    kind = probe.get("subtitle_track_kind")
    if isinstance(kind, str) and kind:
        pipeline_config["subtitle_track_kind"] = kind
    has_sub = probe.get("has_subtitle_stream")
    if has_sub is True:
        pipeline_config["subtitle_stream"] = "true"
    elif has_sub is False:
        pipeline_config["subtitle_stream"] = "false"
    subtitle_codecs = probe.get("subtitle_codecs") or []
    if isinstance(subtitle_codecs, list) and subtitle_codecs:
        pipeline_config["subtitle_codecs"] = ",".join(
            [str(v) for v in subtitle_codecs if str(v).strip()]
        )
    return pipeline_config


def _update_pipeline_probe(repo, task_id: str, probe: dict[str, Any] | None) -> None:
    if not probe:
        return
    task = repo.get(task_id)
    if not task:
        return
    current = parse_pipeline_config(task.get("pipeline_config"))
    updated = _merge_probe_into_pipeline_config(current, probe)
    if updated != current:
        _policy_upsert(repo, task_id, {"pipeline_config": pipeline_config_to_storage(updated)})


def _should_autostart(task: dict) -> bool:
    if not isinstance(task, dict):
        return False
    if task.get("status") in ("processing", "queued") and task.get("last_step"):
        return False
    if any(task.get(k) for k in ("subtitles_status", "dub_status", "pack_status")):
        return False
    return True


def _kickoff_autostart(
    *,
    task_id: str,
    start_step: str,
    reason: str,
    repo,
    background_tasks: BackgroundTasks,
) -> None:
    task = repo.get(task_id)
    if not task or not _should_autostart(task):
        return
    logger.info(
        "AUTO_START",
        extra={"task": task_id, "step": start_step, "phase": "enqueue", "reason": reason},
    )
    if start_step == "parse":
        background_tasks.add_task(_run_pipeline_background, task_id, repo)
        return
    if start_step in {"subtitles", "pipeline"}:
        background_tasks.add_task(auto_run_pipeline, task_id, repo)


def auto_run_pipeline(task_id: str, repo) -> None:
    logger.info("AUTO_PIPELINE_START", extra={"task_id": task_id})
    try:
        task = repo.get(task_id)
        if not task:
            logger.info("AUTO_PIPELINE_DONE", extra={"task_id": task_id, "reason": "missing_task"})
            return

        pipeline_config = parse_pipeline_config(task.get("pipeline_config"))
        default_lang = os.getenv("DEFAULT_MM_LANG", "my")
        target_lang = task.get("content_lang") or default_lang

        has_subs = bool(
            task.get("subtitles_status") == "ready"
            or task.get("origin_srt_path")
            or task.get("mm_srt_path")
        )
        if not has_subs:
            logger.info("AUTO_PIPELINE_STEP", extra={"task_id": task_id, "step": "subtitles"})
            _run_subtitles_job(
                task_id=task_id,
                target_lang=target_lang,
                force=False,
                translate=True,
                repo=repo,
            )
        else:
            logger.info("AUTO_PIPELINE_SKIP", extra={"task_id": task_id, "step": "subtitles"})

        task = repo.get(task_id) or task
        pipeline_config = parse_pipeline_config(task.get("pipeline_config"))
        no_dub = pipeline_config.get("no_dub") == "true"
        has_audio = bool(task.get("mm_audio_path") or task.get("mm_audio_key"))
        if not has_audio and not no_dub:
            logger.info("AUTO_PIPELINE_STEP", extra={"task_id": task_id, "step": "dub"})
            payload = DubProviderRequest()
            asyncio.run(_run_dub_job(task_id, payload, repo))
        else:
            logger.info("AUTO_PIPELINE_SKIP", extra={"task_id": task_id, "step": "dub"})

        task = repo.get(task_id) or task
        has_pack = bool(
            task.get("pack_status") == "ready"
            or task.get("pack_key")
            or task.get("pack_path")
        )
        if not has_pack:
            logger.info("AUTO_PIPELINE_STEP", extra={"task_id": task_id, "step": "pack"})
            _policy_upsert(repo, task_id, {"status": "processing", "last_step": "pack"})
            pack_req = PackRequest(task_id=task_id)
            pack_res = asyncio.run(run_pack_step_v1(pack_req))
            pack_key = None
            if isinstance(pack_res, dict):
                pack_key = pack_res.get("pack_key") or pack_res.get("zip_key")
            _policy_upsert(repo, 
                task_id,
                {
                    "last_step": "pack",
                    "pack_key": pack_key,
                    "pack_type": "capcut_v18" if pack_key else None,
                    "pack_status": "ready" if pack_key else None,
                    "pack_error": None,
                    "status": "done" if pack_key else "processing",
                },
            )
        else:
            logger.info("AUTO_PIPELINE_SKIP", extra={"task_id": task_id, "step": "pack"})
        logger.info("AUTO_PIPELINE_DONE", extra={"task_id": task_id})
    except Exception:
        logger.exception("AUTO_PIPELINE_FAIL", extra={"task_id": task_id})

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
            try:
                probe = probe_subtitles(raw_file)
                _update_pipeline_probe(repo, task_id, probe)
            except Exception:
                logger.exception("SUBTITLE_PROBE_FAIL", extra={"task_id": task_id})
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
            mp3_path = _ensure_mp3_audio(audio_path, workspace.mm_audio_mp3_path)
            audio_key = AUDIO_MM_KEY_TEMPLATE.format(task_id=task_id)
            storage = get_storage_service()
            uploaded_key = storage.upload_file(
                str(mp3_path), audio_key, content_type="audio/mpeg"
            )
            if not uploaded_key:
                raise HTTPException(
                    status_code=500,
                    detail="Audio upload failed; no storage key returned",
                )
        _repo_upsert(
            repo,
            task_id,
            {
                **status_update,
                "last_step": current_step,
                "mm_audio_path": audio_key,
                "mm_audio_key": audio_key,
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
        resp = render_template(
            request=request,
            name="task_not_found.html",
            ctx={"task_id": task_id},
        )
        resp.status_code = 404
        return resp

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
        "pipeline_config": detail.pipeline_config,
        "no_dub": detail.no_dub,
        "dub_skip_reason": detail.dub_skip_reason,
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

    spec = resolve_workbench_spec(task)
    return render_template(
        request=request,
        name=spec.template,
        ctx={
            "task": detail,
            "task_json": task_json,
            "task_view": task_view,
            "env_summary": env_summary,
            "features": get_features(),
            "workbench_kind": spec.kind,
            "workbench_js": spec.js,
        },
    )


@pages_router.get("/tasks/{task_id}/publish", response_class=HTMLResponse)
async def task_publish_hub_page(
    request: Request, task_id: str, repo=Depends(get_task_repository)
) -> HTMLResponse:
    """Render the per-task publish hub page."""

    task = repo.get(task_id)
    if not task:
        resp = render_template(
            request=request,
            name="task_not_found.html",
            ctx={"task_id": task_id},
        )
        resp.status_code = 404
        return resp

    detail = _task_to_detail(task)
    task_json = {"task_id": detail.task_id}
    return render_template(
        request=request,
        name="task_publish_hub.html",
        ctx={
            "task": detail,
            "task_json": task_json,
        },
    )


@pages_router.get("/op/dl/{task_id}")
def op_download_proxy(
    task_id: str,
    kind: str = Query(default=..., min_length=1),
    exp: int | None = Query(default=None),
    sig: str | None = Query(default=None),
    repo=Depends(get_task_repository),
):
    kind = (kind or "").strip().lower()
    kind_map = {
        "raw": "raw",
        "pack": "pack",
        "scenes": "scenes",
        "origin_srt": "origin",
        "mm_srt": "mm",
        "mm_txt": "mm_txt",
        "mm_audio": "audio",
        "publish_bundle": "publish_bundle",
    }
    if kind not in kind_map:
        raise HTTPException(status_code=400, detail="Unsupported kind")
    if _get_op_access_key():
        if exp is None or not sig:
            raise HTTPException(status_code=403, detail="Missing signature")
        now_ts = int(time.time())
        max_ttl = 7 * 24 * 3600
        if exp < now_ts or exp > now_ts + max_ttl:
            raise HTTPException(status_code=403, detail="Expired signature")
        if not _op_verify(task_id, kind, exp, sig):
            raise HTTPException(status_code=403, detail="Invalid signature")

    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    url = _task_endpoint(task_id, kind_map[kind])
    if not url:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    return RedirectResponse(url=url, status_code=302)


@pages_router.get("/d/{code}")
def resolve_download_code(code: str, repo=Depends(get_task_repository)):
    code = (code or "").strip().lower()
    if not code:
        raise HTTPException(status_code=404, detail="Code not found")

    items = sort_tasks_by_created(repo.list())
    for t in items[:200]:
        tid = str(t.get("task_id") or t.get("id") or "")
        if tid and tid.lower().startswith(code):
            signed = _signed_op_url(tid, "publish_bundle")
            return RedirectResponse(url=signed, status_code=302)

    raise HTTPException(status_code=404, detail="Code not found")


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
        "selected_tool_ids": _normalize_selected_tool_ids(payload.selected_tool_ids),
        "pipeline_config": pipeline_config_to_storage(payload.pipeline_config),
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

    if source_text:
        _kickoff_autostart(
            task_id=task_id,
            start_step="parse",
            reason="source_url",
            repo=repo,
            background_tasks=background_tasks,
        )

    return _task_to_detail(stored_task)


def _save_upload_to_paths(
    *,
    upload: UploadFile,
    inputs_path: Path,
    raw_path_target: Path,
    max_bytes: int,
) -> int:
    inputs_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path_target.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with inputs_path.open("wb") as out:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                out.close()
                try:
                    inputs_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise HTTPException(status_code=413, detail="upload too large")
            out.write(chunk)
    if inputs_path != raw_path_target:
        shutil.copyfile(inputs_path, raw_path_target)
    return total


@api_router.post("/tasks/local_upload")
def create_task_local_upload(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    category: str | None = Form(default=None),
    language: str | None = Form(default=None),
    account: str | None = Form(default=None),
    platform: str | None = Form(default=None),
    account_id: str | None = Form(default=None),
    account_name: str | None = Form(default=None),
    video_type: str | None = Form(default=None),
    template: str | None = Form(default=None),
    title: str | None = Form(default=None),
    note: str | None = Form(default=None),
    style_preset: str | None = Form(default=None),
    subtitles_mode: str | None = Form(default=None),
    dub_mode: str | None = Form(default=None),
    repo=Depends(get_task_repository),
):
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="file is required")

    ext = Path(file.filename).suffix.lower()
    if ext not in {".mp4", ".mov", ".mkv"}:
        raise HTTPException(status_code=400, detail="unsupported file type")

    task_id = uuid4().hex[:12]
    max_mb = int(os.getenv("MAX_LOCAL_UPLOAD_MB", "200"))
    max_bytes = max_mb * 1024 * 1024

    raw_file_path = raw_path(task_id)
    _save_upload_to_paths(
        upload=file,
        inputs_path=raw_file_path,
        raw_path_target=raw_file_path,
        max_bytes=max_bytes,
    )
    probe = None
    try:
        probe = probe_subtitles(raw_file_path)
    except Exception:
        logger.exception("SUBTITLE_PROBE_FAIL", extra={"task_id": task_id})

    if account and not account_id:
        account_id = account
    if account and not account_name:
        account_name = account

    platform_value = platform or "local"
    pipeline_config = _merge_probe_into_pipeline_config(
        {
            "subtitles_mode": subtitles_mode or "whisper+gemini",
            "dub_mode": dub_mode or "auto-fallback",
            "ingest_mode": "local",
        },
        probe,
    )
    task_payload = {
        "task_id": task_id,
        "title": title,
        "source_url": None,
        "platform": platform_value,
        "account_id": account_id,
        "account_name": account_name,
        "video_type": video_type,
        "template": template,
        "category_key": category or "suitcase",
        "content_lang": language or "mm",
        "ui_lang": "zh",
        "style_preset": style_preset,
        "face_swap_enabled": False,
        "selected_tool_ids": None,
        "pipeline_config": pipeline_config_to_storage(pipeline_config),
        "status": "pending",
        "last_step": None,
        "error_message": None,
        "source_type": "local",
        "source_filename": file.filename,
        "note": note,
    }
    task_payload = normalize_task_payload(task_payload, is_new=True)
    repo.create(task_payload)
    stored_task = repo.get(task_id)
    if not stored_task:
        raise HTTPException(
            status_code=500,
            detail=f"Task persistence failed for task_id={task_id}",
        )
    if probe:
        _update_pipeline_probe(repo, task_id, probe)

    raw_key = upload_task_artifact(stored_task, raw_file_path, "raw.mp4", task_id=task_id)
    _policy_upsert(repo, 
        task_id,
        {
            "raw_path": raw_key,
            "error_message": None,
            "error_reason": None,
        },
    )

    if background_tasks is not None:
        _kickoff_autostart(
            task_id=task_id,
            start_step="pipeline",
            reason="local_upload",
            repo=repo,
            background_tasks=background_tasks,
        )

    return {"ok": True, "task_id": task_id, "redirect": f"/tasks/{task_id}"}


@api_router.patch("/tasks/{task_id}", response_model=TaskDetail)
def update_task_selected_tools(
    task_id: str,
    payload: TaskUpdate,
    repo=Depends(get_task_repository),
):
    updates: dict[str, Any] = {}
    if payload.selected_tool_ids is not None:
        updates["selected_tool_ids"] = _normalize_selected_tool_ids(payload.selected_tool_ids)
    if payload.pipeline_config is not None:
        updates["pipeline_config"] = pipeline_config_to_storage(payload.pipeline_config)
    if not updates:
        raise HTTPException(status_code=400, detail="No updatable fields provided")

    _policy_upsert(repo, task_id, updates)
    updated = repo.get(task_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_detail(updated)


@api_router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    account_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    kind: Optional[str] = Query(default=None),
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
    kind_norm = (kind or "").strip().lower()
    if kind_norm:
        if kind_norm == "apollo_avatar":
            items = [
                t
                for t in items
                if (str(t.get("platform") or "").lower() == "apollo_avatar")
                or (str(t.get("category_key") or "").lower() == "apollo_avatar")
            ]
        else:
            items = [
                t
                for t in items
                if str(t.get("category_key") or "").lower() == kind_norm
                or str(t.get("platform") or "").lower() == kind_norm
            ]
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
                selected_tool_ids=_normalize_selected_tool_ids(t.get("selected_tool_ids")),
                pipeline_config=parse_pipeline_config(t.get("pipeline_config")),
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
def save_mm_edited(task_id: str, payload: EditedTextRequest, repo=Depends(get_task_repository)):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")
    path = _mm_edited_path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(text + "\n", encoding="utf-8")
        task = repo.get(task_id) if repo else None
        if task:
            workspace = Workspace(task_id)
            mm_txt_path = workspace.mm_txt_path
            mm_txt_path.parent.mkdir(parents=True, exist_ok=True)
            mm_txt_path.write_text(text + "\n", encoding="utf-8")
            mm_srt_key = _task_value(task, "mm_srt_path")
            artifact_name = "mm.txt"
            if isinstance(mm_srt_key, str):
                normalized_key = mm_srt_key.replace("\\", "/")
                if "subs/" in normalized_key:
                    artifact_name = "subs/mm.txt"
            mm_txt_key = upload_task_artifact(
                task,
                mm_txt_path,
                artifact_name,
                task_id=task_id,
            )
            if mm_txt_key and (
                (isinstance(task, dict) and "mm_txt_path" in task)
                or hasattr(task, "mm_txt_path")
            ):
                _policy_upsert(repo, task_id, {"mm_txt_path": mm_txt_key})
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

    detail = _task_to_detail(t)
    updated_at = getattr(detail, "updated_at", None)
    updated_ts = None
    if updated_at:
        try:
            updated_ts = (
                updated_at.replace(tzinfo=timezone.utc).timestamp()
                if updated_at.tzinfo is None
                else updated_at.timestamp()
            )
        except Exception:
            updated_ts = None
    now_ts = datetime.now(timezone.utc).timestamp()
    running = any(
        getattr(detail, key, None) == "running"
        for key in ("subtitles_status", "dub_status", "scenes_status", "pack_status")
    )
    stale_for = int(max(0, now_ts - updated_ts)) if updated_ts and running else 0
    stale = bool(running and updated_ts and stale_for > 1800)

    payload = detail.dict()
    for key in (
        "status",
        "last_step",
        "subtitles_status",
        "dub_status",
        "scenes_status",
        "pack_status",
        "subtitles_error",
        "dub_error",
        "scenes_error",
        "pack_error",
        "raw_path",
        "origin_srt_path",
        "mm_srt_path",
        "mm_txt_path",
        "mm_audio_path",
        "pack_path",
        "scenes_path",
        "updated_at",
    ):
        payload.setdefault(key, None)

    payload["stale"] = stale
    payload["stale_reason"] = "running_but_not_updated" if stale else None
    payload["stale_for_seconds"] = stale_for

    if payload.get("subtitles_status") in (None, "error"):
        if payload.get("origin_srt_path") or payload.get("mm_srt_path") or payload.get("mm_txt_path"):
            payload["subtitles_status"] = "ready"
            payload["subtitles_error"] = None

    if payload.get("dub_status") in (None, "error"):
        if payload.get("mm_audio_path") or payload.get("no_dub") is True:
            payload["dub_status"] = "ready"
            payload["dub_error"] = None

    logger.info(
        "task_status_shape",
        extra={
            "task_id": task_id,
            "status": payload.get("status"),
            "last_step": payload.get("last_step"),
            "subtitles_status": payload.get("subtitles_status"),
            "dub_status": payload.get("dub_status"),
            "scenes_status": payload.get("scenes_status"),
            "pack_status": payload.get("pack_status"),
            "stale": payload.get("stale"),
        },
    )

    return payload


@api_router.get("/tasks/{task_id}/events")
def get_task_events(
    task_id: str,
    repo=Depends(get_task_repository),
):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    kind = task.get("kind") if isinstance(task, dict) else getattr(task, "kind", None)
    return {"task_id": task_id, "kind": kind, "events": task.get("events") or []}


@api_router.get("/tasks/{task_id}/publish_hub")
def get_publish_hub(
    request: Request,
    task_id: str,
    repo=Depends(get_task_repository),
    op_key: str | None = Security(api_key_header),
):
    if not _op_key_valid_value(op_key):
        raise HTTPException(status_code=401, detail="OP key required")
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _publish_hub_payload(task)


@api_router.post("/tasks/{task_id}/parse")
def build_parse(
    task_id: str,
    payload: ParseTaskRequest | None = None,
    repo=Depends(get_task_repository),
):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    pipeline_config = parse_pipeline_config(task.get("pipeline_config"))
    if pipeline_config.get("ingest_mode") == "local":
        _policy_upsert(repo, 
            task_id,
            {
                "status": task.get("status") or "processing",
                "last_step": "parse",
                "error_message": None,
                "error_reason": None,
            },
        )
        stored = repo.get(task_id)
        return _task_to_detail(stored)

    link = task.get("source_url") or task.get("link")
    if not link:
        raise HTTPException(status_code=400, detail="source_url is empty; cannot parse")

    platform = (payload.platform if payload else None) or task.get("platform")
    _policy_upsert(repo, task_id, {"status": "processing", "last_step": "parse"})
    parse_req = ParseRequest(task_id=task_id, platform=platform, link=link)

    try:
        parse_res = asyncio.run(run_parse_step_v1(parse_req))
    except HTTPException as exc:
        _policy_upsert(repo, 
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
        try:
            probe = probe_subtitles(raw_file)
            _update_pipeline_probe(repo, task_id, probe)
        except Exception:
            logger.exception("SUBTITLE_PROBE_FAIL", extra={"task_id": task_id})
    duration_sec = parse_res.get("duration_sec") if isinstance(parse_res, dict) else None
    _policy_upsert(repo, 
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


def _run_subtitles_job(
    *,
    task_id: str,
    target_lang: str,
    force: bool,
    translate: bool,
    repo,
):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    asyncio.run(
        run_subtitles_step_entry(
            task_id=task_id,
            target_lang=target_lang,
            force=force,
            translate=translate,
        )
    )

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

    _policy_upsert(repo, 
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

    stored = repo.get(task_id)
    return _task_to_detail(stored)


def _run_subtitles_background(
    task_id: str,
    target_lang: str,
    force: bool,
    translate: bool,
    repo,
) -> None:
    try:
        _run_subtitles_job(
            task_id=task_id,
            target_lang=target_lang,
            force=force,
            translate=translate,
            repo=repo,
        )
    except HTTPException as exc:
        _policy_upsert(repo, 
            task_id,
            {"subtitles_status": "error", "subtitles_error": f"{exc.status_code}: {exc.detail}"},
        )
        logger.exception(
            "SUB2_FAIL",
            extra={
                "task_id": task_id,
                "step": "subtitles",
                "phase": "exception",
            },
        )


async def _run_dub_job(task_id: str, payload: DubProviderRequest, repo: ITaskRepository) -> DubResponse:
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    settings = get_settings()
    provider_raw = payload.provider
    if not provider_raw:
        pipeline_config = parse_pipeline_config(task.get("pipeline_config"))
        dub_mode = pipeline_config.get("dub_mode")
        if dub_mode == "edge":
            provider_raw = "edge-tts"
        elif dub_mode == "lovo":
            provider_raw = "lovo"
        else:
            provider_raw = "lovo" if getattr(settings, "lovo_api_key", None) else "edge-tts"
    if not provider_raw:
        provider_raw = "edge-tts"
    provider_norm = provider_raw.lower().replace("-", "_")
    if provider_norm == "edge":
        provider_norm = "edge_tts"
    if provider_norm not in {"edge_tts", "lovo"}:
        raise HTTPException(status_code=400, detail="Unsupported dub provider")
    provider = "edge-tts" if provider_norm == "edge_tts" else "lovo"

    if provider == "lovo" and not getattr(settings, "lovo_api_key", None):
        raise HTTPException(status_code=400, detail="LOVO_API_KEY is not configured")

    req_voice_id = payload.voice_id or None
    prev_voice_id = task.get("voice_id") if isinstance(task, dict) else getattr(task, "voice_id", None)
    final_voice_id = req_voice_id or prev_voice_id or "mm_female_1"
    mm_text_override = (payload.mm_text or "").strip() or None
    workspace = Workspace(task_id)
    audio_present = False
    if isinstance(task, dict):
        audio_present = bool(task.get("mm_audio_key") or task.get("mm_audio_path"))
    else:
        audio_present = bool(
            getattr(task, "mm_audio_key", None) or getattr(task, "mm_audio_path", None)
        )
    audio_present = audio_present or workspace.mm_audio_exists()
    voice_changed = bool(req_voice_id and req_voice_id != prev_voice_id)
    force_dub = bool(audio_present and voice_changed)

    edge_voice = None
    if provider == "edge-tts":
        edge_voice = settings.edge_tts_voice_map.get(final_voice_id, final_voice_id)

    logger.info(
        "dub: task=%s req_voice_id=%s prev_voice_id=%s final_voice_id=%s edge_voice=%s",
        task_id,
        req_voice_id,
        prev_voice_id,
        final_voice_id,
        edge_voice,
    )

    try:
        class TaskAdapter:
            def __init__(
                self,
                t: dict,
                voice_override: str | None,
                provider: str,
                force_dub: bool,
                mm_text: str | None,
            ):
                self.task_id = t.get("task_id") or t.get("id")
                self.id = self.task_id
                self.tenant_id = t.get("tenant_id") or t.get("tenant") or "default"
                self.project_id = t.get("project_id") or t.get("project") or "default"
                self.target_lang = t.get("target_lang") or t.get("content_lang") or "my"
                self.voice_id = voice_override or t.get("voice_id")
                self.dub_provider = provider
                self.force_dub = force_dub
                self.mm_text = mm_text

        task_adapter = TaskAdapter(
            task,
            voice_override=final_voice_id,
            provider=provider,
            force_dub=force_dub,
            mm_text=mm_text_override,
        )

        # 核心：SSOT dubbing
        await run_dub_step_ssot(task_adapter)

        task_after = repo.get(task_id) or {}
        pipeline_config = parse_pipeline_config(task_after.get("pipeline_config"))
        no_dub_flag = pipeline_config.get("no_dub") == "true"
        no_dub_note = (task_base_dir(task_id) / "dub" / "no_dub.txt").exists()
        if no_dub_flag or no_dub_note:
            audio_key = task_after.get("mm_audio_key") or task_after.get("mm_audio_path")
            audio_sha256 = None
            if not audio_key:
                audio_path = (
                    workspace.mm_audio_mp3_path
                    if workspace.mm_audio_mp3_path.exists()
                    else workspace.mm_audio_path
                )
                if audio_path.exists():
                    audio_key = AUDIO_MM_KEY_TEMPLATE.format(task_id=task_id)
                    storage = get_storage_service()
                    storage.upload_file(str(audio_path), audio_key, content_type="audio/mpeg")
                    audio_sha256 = _sha256_file(audio_path)
            _policy_upsert(repo, 
                task_id,
                {
                    "mm_audio_path": audio_key,
                    "mm_audio_key": audio_key,
                    "dub_provider": provider,
                    "last_step": "dubbing",
                    "voice_id": final_voice_id,
                    "dub_status": "ready",
                    "dub_error": None,
                },
            )
            stored = repo.get(task_id)
            detail = _task_to_detail(stored)
            detail.audio_sha256 = audio_sha256
            return detail

        audio_path = (
            workspace.mm_audio_mp3_path
            if workspace.mm_audio_mp3_path.exists()
            else workspace.mm_audio_path
        )
        if not audio_path.exists():
            raise HTTPException(status_code=500, detail="Dubbing output missing")

        audio_key = AUDIO_MM_KEY_TEMPLATE.format(task_id=task_id)
        storage = get_storage_service()
        storage.upload_file(str(audio_path), audio_key, content_type="audio/mpeg")
        audio_sha256 = _sha256_file(audio_path)

    except HTTPException as exc:
        _policy_upsert(repo, task_id, {"dub_status": "error", "dub_error": f"{exc.status_code}: {exc.detail}"})
        raise
    except Exception as exc:
        _policy_upsert(repo, task_id, {"dub_status": "error", "dub_error": str(exc)})
        logger.exception("DUB3_FAIL", extra={"task_id": task_id, "step": "dub", "phase": "exception"})
        raise HTTPException(status_code=500, detail=f"Dubbing step failed: {exc}")

    # repo.update 未必存在；用 upsert 更稳
    _policy_upsert(repo, 
        task_id,
        {
            "mm_audio_path": audio_key,
            "mm_audio_key": audio_key,
            "dub_provider": provider,
            "last_step": "dubbing",
            "voice_id": final_voice_id,
            "dub_status": "ready",
            "dub_error": None,
        },
    )

    stored = repo.get(task_id)
    detail = _task_to_detail(stored)
    return DubResponse(
        **detail.dict(exclude={"mm_audio_key"}),
        resolved_voice_id=final_voice_id,
        resolved_edge_voice=edge_voice,
        audio_sha256=audio_sha256,
        mm_audio_key=audio_key,
    )


def _run_dub_background(task_id: str, payload: DubProviderRequest, repo: ITaskRepository) -> None:
    try:
        asyncio.run(_run_dub_job(task_id, payload, repo))
    except Exception:
        logger.exception("DUB3_FAIL", extra={"task_id": task_id, "step": "dub", "phase": "exception"})
    except Exception as exc:
        _policy_upsert(repo, task_id, {"subtitles_status": "error", "subtitles_error": str(exc)})
        logger.exception(
            "SUB2_FAIL",
            extra={
                "task_id": task_id,
                "step": "subtitles",
                "phase": "exception",
            },
        )


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

    def _update(task_id: str, fields: dict) -> None:
        _policy_upsert(repo, task_id, fields)

    return enqueue_scenes_build(
        task_id,
        task=task,
        object_exists=object_exists,
        update_task=_update,
        background_tasks=background_tasks,
    )

@api_router.post("/tasks/{task_id}/pack")
def build_pack(
    task_id: str,
    repo=Depends(get_task_repository),
):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    _policy_upsert(repo, task_id, {"status": "processing", "last_step": "pack"})
    pack_req = PackRequest(task_id=task_id)
    try:
        pack_res = asyncio.run(run_pack_step_v1(pack_req))
    except HTTPException as exc:
        _policy_upsert(repo, 
            task_id,
            {
                "status": "failed",
                "last_step": "pack",
                "error_message": str(exc.detail),
                "error_reason": "pack_failed",
            },
        )
        raise

    pack_key = None
    if isinstance(pack_res, dict):
        pack_key = pack_res.get("pack_key") or pack_res.get("zip_key")
    _policy_upsert(repo, 
        task_id,
        {
            "status": "ready",
            "last_step": "pack",
            "pack_key": pack_key,
            "pack_type": "capcut_v18" if pack_key else None,
            "pack_status": "ready" if pack_key else None,
            "error_message": None,
            "error_reason": None,
        },
    )

    stored = repo.get(task_id)
    return _task_to_detail(stored)

@api_router.post("/tasks/{task_id}/dub", response_model=DubResponse)
async def rerun_dub(
    task_id: str,
    payload: DubProviderRequest,
    background_tasks: BackgroundTasks,
    repo: ITaskRepository = Depends(get_task_repository),
):
    """Re-run dubbing for a task (SSOT: reads artifacts/subtitles.json)."""

    t0 = time.perf_counter()
    try:
        task = repo.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        run_async = os.getenv("RUN_STEPS_ASYNC", "1").strip().lower() not in ("0", "false", "no")
        _policy_upsert(repo, task_id, {"dub_status": "running", "dub_error": None, "last_step": "dub"})

        if run_async:
            background_tasks.add_task(_run_dub_background, task_id, payload, repo)
            return JSONResponse(status_code=202, content={"queued": True, "task_id": task_id})

        return await _run_dub_job(task_id, payload, repo)
    finally:
        logger.info(
            "dub request finished",
            extra={
                "task_id": task_id,
                "step": "dub",
                "phase": "request_end",
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            },
        )


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
            task_repo=repo,
            provider=(payload.provider if payload else None),
            force=(payload.force if payload else False),
        )
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if task:
            _policy_upsert(repo, 
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
def build_subtitles(
    task_id: str,
    background_tasks: BackgroundTasks,
    payload: SubtitlesTaskRequest | None = None,
    repo=Depends(get_task_repository),
):
    t0 = time.perf_counter()
    try:
        task = repo.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        if task.get("subtitles_status") == "ready" and task.get("subtitles_key"):
            return {
                "task_id": task_id,
                "status": "already_ready",
                "subtitles_key": task.get("subtitles_key"),
                "message": "Subtitles already ready",
                "error": None,
            }

        target_lang, force, translate = compute_subtitles_params(task, payload)

        run_async = os.getenv("RUN_STEPS_ASYNC", "1").strip().lower() not in ("0", "false", "no")
        _policy_upsert(repo, 
            task_id,
            {
                "subtitles_status": "running",
                "subtitles_error": None,
                "last_step": "subtitles",
            },
        )

        if run_async:
            background_tasks.add_task(
                _run_subtitles_background,
                task_id,
                target_lang,
                force,
                translate,
                repo,
            )
            return JSONResponse(status_code=202, content={"queued": True, "task_id": task_id})

        return _run_subtitles_job(
            task_id=task_id,
            target_lang=target_lang,
            force=force,
            translate=translate,
            repo=repo,
        )
    finally:
        logger.info(
            "subtitles request finished",
            extra={
                "task_id": task_id,
                "step": "subtitles",
                "phase": "request_end",
                "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            },
        )



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
