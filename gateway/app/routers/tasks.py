"""Task API and HTML routers for the gateway application."""

import re
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from ..config import get_settings
from ..core.features import get_features
from gateway.app.web.templates import get_templates
from gateway.app.deps import get_task_repository
from ..schemas import TaskCreate, TaskDetail, TaskListResponse, TaskSummary
from gateway.app.task_repo_utils import normalize_task_payload, sort_tasks_by_created
from ..services.pipeline_v1 import run_pipeline_background
from ..core.workspace import (
    Workspace,
    origin_srt_path,
    pack_zip_path,
    relative_to_workspace,
    translated_srt_path,
)



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
                "pack_path": str(t.get("pack_path")) if t.get("pack_path") else None,
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


def _resolve_paths(task: dict) -> dict[str, Optional[str]]:
    task_id = str(task.get("task_id") or task.get("id"))
    workspace = Workspace(task_id)

    # Prefer stored DB paths; otherwise expose workspace-relative paths if files exist.
    raw_video = task.get("raw_path") or None
    if not raw_video and workspace.raw.exists():
        raw_video = relative_to_workspace(workspace.raw)

    origin_srt = translated_srt = None
    origin_srt = task.get("origin_srt_path")
    translated_srt = task.get("mm_srt_path")

    # Fall back to workspace artifacts when present.
    if not origin_srt:
        path = origin_srt_path(task_id)
        if path.exists():
            origin_srt = relative_to_workspace(path)
    if not translated_srt:
        path = workspace.mm_srt_path
        if path.exists():
            translated_srt = relative_to_workspace(path)

    mm_audio = task.get("mm_audio_path") or None
    if workspace.mm_audio_exists():
        from ..core.workspace import ensure_public_audio

        ensure_public_audio(workspace.mm_audio_path)
        if not mm_audio:
            mm_audio = f"audio/{workspace.mm_audio_path.name}"

    pack_path = task.get("pack_path") or None
    if not pack_path:
        pack = pack_zip_path(task_id)
        if pack.exists():
            pack_path = relative_to_workspace(pack)

    return {
        "raw_path": raw_video,
        "origin_srt_path": origin_srt,
        "mm_srt_path": translated_srt,
        "mm_audio_path": mm_audio,
        "pack_path": pack_path,
    }


def _task_to_detail(task: dict) -> TaskDetail:
    paths = _resolve_paths(task)
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

    background_tasks.add_task(run_pipeline_background, db_task.id)

    return _task_to_detail(task_payload)


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
        pack_path = str(t.get("pack_path")) if t.get("pack_path") else None
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


@api_router.get("/tasks/{task_id}", response_model=TaskDetail)
def get_task(task_id: str, repo=Depends(get_task_repository)):
    """Retrieve a single task by id."""

    t = repo.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")

    return _task_to_detail(t)


# Backwards-compatible export for existing imports
router = api_router

__all__ = ["api_router", "pages_router", "router"]
