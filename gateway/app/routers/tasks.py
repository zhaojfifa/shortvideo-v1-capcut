"""Task API and HTML routers for the gateway application."""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from pydantic import BaseModel
from ..config import get_settings
from ..core.features import get_features
from gateway.app.web.templates import get_templates
from gateway.app.deps import get_task_repository
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
from gateway.app.task_repo_utils import normalize_task_payload, sort_tasks_by_created
from gateway.app.services.dubbing import DubbingError, synthesize_voice
from gateway.app.services.artifact_storage import upload_task_artifact
from gateway.app.services.artifact_storage import get_download_url, get_object_bytes, object_exists
from gateway.app.services.task_cleanup import delete_task_record, purge_task_artifacts
from ..services.steps_v1 import (
    run_dub_step,
    run_pack_step,
    run_parse_step,
    run_subtitles_step,
)
from ..core.workspace import (
    Workspace,
    origin_srt_path,
    pack_zip_path,
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


pages_router = APIRouter()
api_router = APIRouter(prefix="/api", tags=["tasks"])
templates = get_templates()


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
    task_id = str(task.get("task_id") or task.get("id") or "")
    pack_path = task.get("pack_path")
    if pack_path:
        pack_path = str(pack_path)
        if pack_path.startswith(("pack/", "published/")) and not _is_storage_key(pack_path):
            return pack_path
    pack_file = pack_zip_path(task_id)
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
    key = _require_storage_key(task, "pack_path", "Pack not found")
    return RedirectResponse(url=get_download_url(key), status_code=302)


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
    return None


def _task_key(task: dict, field: str) -> Optional[str]:
    value = task.get(field)
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
    pack_url = (
        _task_endpoint(task_id, "pack")
        if task.get("pack_path")
        else None
    )

    return {
        "raw_path": raw_url,
        "origin_srt_path": origin_url,
        "mm_srt_path": mm_url,
        "mm_audio_path": audio_url,
        "mm_txt_path": mm_txt_url,
        "pack_path": pack_url,
    }


def _task_to_detail(task: dict) -> TaskDetail:
    paths = _resolve_download_urls(task)
    status = task.get("status") or "pending"
    if status != "error" and paths["pack_path"]:
        status = "ready"

    return TaskDetail(
        task_id=str(task.get("task_id") or task.get("id")),
        title=task.get("title"),
        source_url=str(task.get("source_url")) if task.get("source_url") else None,
        source_link_url=_extract_first_http_url(task.get("source_url")),
        platform=task.get("platform"),
        account_id=task.get("account_id"),
        account_name=task.get("account_name"),
        video_type=task.get("video_type"),
        template=task.get("template"),
        category_key=task.get("category_key") or "beauty",
        content_lang=task.get("content_lang") or "my",
        ui_lang=task.get("ui_lang") or "en",
        style_preset=task.get("style_preset"),
        face_swap_enabled=bool(task.get("face_swap_enabled")),
        status=status,
        last_step=task.get("last_step"),
        duration_sec=task.get("duration_sec"),
        thumb_url=task.get("thumb_url"),
        raw_path=paths["raw_path"],
        origin_srt_path=paths["origin_srt_path"],
        mm_srt_path=paths["mm_srt_path"],
        mm_audio_path=paths["mm_audio_path"],
        pack_path=paths["pack_path"],
        created_at=task.get("created_at"),
        error_message=task.get("error_message"),
        error_reason=task.get("error_reason"),
        parse_provider=task.get("parse_provider"),
        subtitles_provider=task.get("subtitles_provider"),
        dub_provider=task.get("dub_provider"),
        pack_provider=task.get("pack_provider"),
        face_swap_provider=task.get("face_swap_provider"),
        publish_status=task.get("publish_status"),
        publish_provider=task.get("publish_provider"),
        publish_key=task.get("publish_key"),
        publish_url=task.get("publish_url"),
        published_at=task.get("published_at"),
        priority=task.get("priority"),
        assignee=task.get("assignee"),
        ops_notes=task.get("ops_notes"),
    )


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
        parse_res = asyncio.run(run_parse_step(parse_req))
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
        asyncio.run(run_subtitles_step(subs_req))
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
        asyncio.run(run_dub_step(dub_req))
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
        asyncio.run(run_pack_step(pack_req))
        pack_file = pack_zip_path(task_id)
        pack_key = None
        if pack_file.exists():
            pack_key = upload_task_artifact(task, pack_file, "capcut_pack.zip", task_id=task_id)
        _repo_upsert(
            repo,
            task_id,
            {
                "status": "done",
                "last_step": current_step,
                "pack_path": pack_key,
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
                created_at=t.get("created_at"),
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
):
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


@api_router.post("/tasks/{task_id}/dub", response_model=TaskDetail)
def rerun_dub(
    task_id: str,
    payload: DubProviderRequest,
    repo=Depends(get_task_repository),
):
    """Re-run dubbing for a task with a selected provider."""

    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    provider = (payload.provider or "edge-tts").lower()
    if provider == "edge":
        provider = "edge-tts"
    if provider not in {"edge-tts", "lovo"}:
        raise HTTPException(status_code=400, detail="Unsupported dub provider")

    settings = get_settings()
    if provider == "lovo" and not settings.lovo_api_key:
        raise HTTPException(status_code=400, detail="LOVO_API_KEY is not configured")

    try:
        dub_text, _source = _load_dub_text(task_id)
        if not dub_text.strip():
            raise HTTPException(
                status_code=400,
                detail="dub text missing: mm_edited.txt/mm.txt not found or empty",
            )
        result = asyncio.run(
            synthesize_voice(
                task_id=task_id,
                target_lang=task.get("content_lang") or "my",
                voice_id=payload.voice_id,
                force=True,
                mm_srt_text=dub_text,
                provider=provider,
            )
        )
    except DubbingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audio_key = None
    audio_path = result.get("path")
    if audio_path:
        audio_key = upload_task_artifact(task, Path(audio_path), "mm_audio.mp3", task_id=task_id)
    repo.update(
        task_id,
        {
            "mm_audio_path": audio_key,
            "dub_provider": provider,
        },
    )
    stored = repo.get(task_id) or task
    return _task_to_detail(stored)


@api_router.get("/tasks/{task_id}", response_model=TaskDetail)
def get_task(task_id: str, repo=Depends(get_task_repository)):
    """Retrieve a single task by id."""

    t = repo.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")

    return _task_to_detail(t)


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


# Backwards-compatible export for existing imports
router = api_router

__all__ = ["api_router", "pages_router", "router"]
