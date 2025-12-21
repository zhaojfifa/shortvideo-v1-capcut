"""Task API router and simple HTML task board page."""

from pathlib import Path
import re
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from gateway.app.config import get_settings
from gateway.app.core.features import get_features
from gateway.app.core.workspace import (
    Workspace,
    origin_srt_path,
    pack_zip_path,
    relative_to_workspace,
    translated_srt_path,
)
from gateway.app.deps import get_task_repository
from gateway.app.web.templates import get_templates
from gateway.app.schemas import TaskCreate, TaskDetail, TaskListResponse, TaskSummary
from gateway.app.task_repo_utils import normalize_task_payload, sort_tasks_by_created
from gateway.app.services.pipeline_v1 import run_pipeline_background

router = APIRouter(prefix="/tasks")
pages_router = APIRouter()

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
async def tasks_board_page(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    repo=Depends(get_task_repository),
):
    """Render the task board HTML without preloading ORM tasks."""

    return templates.TemplateResponse(
        "tasks_board.html",
        {"request": request, "tasks": []},
    )


@pages_router.get("/tasks/new", response_class=HTMLResponse)
async def tasks_new(request: Request) -> HTMLResponse:
    """Render suitcase quick-create page."""

    return templates.TemplateResponse(
        "tasks_new.html",
        {"request": request, "features": get_features()},
    )


@pages_router.get("/m", response_class=HTMLResponse)
async def tasks_mobile_root():
    return RedirectResponse("/m/tasks")


@pages_router.get("/m/tasks", response_class=HTMLResponse)
async def tasks_board_mobile(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    repo=Depends(get_task_repository),
):
    response = await tasks_board_page(request, repo=repo, limit=limit)
    response.context["is_mobile"] = True
    response.context["view"] = "mobile"
    return response


@pages_router.get("/m/tasks/new", response_class=HTMLResponse)
async def tasks_new_mobile(request: Request) -> HTMLResponse:
    response = await tasks_new(request)
    response.context["is_mobile"] = True
    response.context["view"] = "mobile"
    return response


def _resolve_paths(task: dict) -> dict[str, Optional[str]]:
    task_id = str(task.get("task_id") or task.get("id"))
    workspace = Workspace(task_id)
    raw_video = task.get("raw_path") or None
    if not raw_video and workspace.raw.exists():
        raw_video = relative_to_workspace(workspace.raw)

    origin_srt = task.get("origin_srt_path")
    mm_srt = task.get("mm_srt_path")
    if not origin_srt:
        path = origin_srt_path(task_id)
        if path.exists():
            origin_srt = relative_to_workspace(path)
    if not mm_srt:
        path = translated_srt_path(task_id, "mm")
        if path.exists():
            mm_srt = relative_to_workspace(path)

    mm_audio = task.get("mm_audio_path") or None
    if not mm_audio and workspace.mm_audio_exists():
        mm_audio = relative_to_workspace(workspace.mm_audio_path)

    pack_path = task.get("pack_path") or None
    if not pack_path:
        pack = pack_zip_path(task_id)
        if pack.exists():
            pack_path = relative_to_workspace(pack)

    return {
        "raw_path": raw_video,
        "origin_srt_path": origin_srt,
        "mm_srt_path": mm_srt,
        "mm_audio_path": mm_audio,
        "pack_path": pack_path,
    }


def _extract_first_http_url(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"https?://\\S+", text)
    return match.group(0) if match else None


@pages_router.get("/tasks/{task_id}", response_class=HTMLResponse)
async def task_workbench_page(
    request: Request, task_id: str, repo=Depends(get_task_repository)
) -> HTMLResponse:
    task = repo.get(task_id)
    if not task:
        return templates.TemplateResponse(
            "task_not_found.html",
            {"request": request, "task_id": task_id},
            status_code=404,
        )

    paths = _resolve_paths(task)
    task_json = {
        "task_id": task.get("task_id") or task.get("id"),
        "status": task.get("status"),
        "platform": task.get("platform"),
        "category_key": task.get("category_key"),
        "content_lang": task.get("content_lang"),
        "ui_lang": task.get("ui_lang"),
        "source_url": task.get("source_url"),
        "raw_path": paths["raw_path"],
        "origin_srt_path": paths["origin_srt_path"],
        "mm_srt_path": paths["mm_srt_path"],
        "mm_audio_path": paths["mm_audio_path"],
        "pack_path": paths["pack_path"],
    }
    task_view = {"source_url_open": _extract_first_http_url(task.get("source_url"))}

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

    return templates.TemplateResponse(
        "task_workbench.html",
        {
            "request": request,
            "task": task,
            "task_json": task_json,
            "task_view": task_view,
            "env_summary": env_summary,
            "features": get_features(),
        },
    )


@pages_router.get("/m/tasks/{task_id}", response_class=HTMLResponse)
async def task_workbench_mobile(
    request: Request, task_id: str, repo=Depends(get_task_repository)
) -> HTMLResponse:
    response = await task_workbench_page(request, task_id=task_id, repo=repo)
    response.context["is_mobile"] = True
    response.context["view"] = "mobile"
    return response


@router.post("", response_model=TaskDetail)
def create_task(
    payload: TaskCreate,
    background_tasks: BackgroundTasks,
    repo=Depends(get_task_repository),
):
    """
    Create a Task record and kick off the V1 pipeline asynchronously.
    """

    platform = payload.platform or _infer_platform_from_url(str(payload.source_url))
    task_id = uuid4().hex[:12]

    task_payload = {
        "task_id": task_id,
        "title": payload.title,
        "source_url": str(payload.source_url),
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

    background_tasks.add_task(run_pipeline_background, task_id)

    return TaskDetail(
        task_id=task_payload["task_id"],
        title=task_payload.get("title"),
        platform=task_payload.get("platform"),
        account_id=task_payload.get("account_id"),
        account_name=task_payload.get("account_name"),
        video_type=task_payload.get("video_type"),
        template=task_payload.get("template"),
        category_key=task_payload.get("category_key") or "beauty",
        content_lang=task_payload.get("content_lang") or "my",
        ui_lang=task_payload.get("ui_lang") or "en",
        style_preset=task_payload.get("style_preset"),
        face_swap_enabled=bool(task_payload.get("face_swap_enabled")),
        status=task_payload.get("status"),
        last_step=task_payload.get("last_step"),
        duration_sec=task_payload.get("duration_sec"),
        thumb_url=task_payload.get("thumb_url"),
        raw_path=task_payload.get("raw_path"),
        mm_audio_path=task_payload.get("mm_audio_path"),
        pack_path=task_payload.get("pack_path"),
        created_at=task_payload.get("created_at"),
        error_message=task_payload.get("error_message"),
        error_reason=task_payload.get("error_reason"),
    )


@router.get("", response_model=TaskListResponse)
def list_tasks(
    account_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
    repo=Depends(get_task_repository),
):
    """
    List tasks ordered by creation time (newest first) with an adjustable limit.
    """

    filters = {}
    if account_id:
        filters["account_id"] = account_id
    if status:
        filters["status"] = status

    items = sort_tasks_by_created(repo.list(filters=filters))
    total = len(items)
    items = items[(page - 1) * limit : (page - 1) * limit + limit]

    summaries: list[TaskSummary] = []
    for t in items:
        summaries.append(
            TaskSummary(
                task_id=t.get("task_id") or t.get("id"),
                title=t.get("title"),
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
                status=t.get("status"),
                last_step=t.get("last_step"),
                duration_sec=t.get("duration_sec"),
                thumb_url=t.get("thumb_url"),
                pack_path=t.get("pack_path"),
                created_at=t.get("created_at"),
                error_message=t.get("error_message"),
                error_reason=t.get("error_reason"),
            )
        )

    return TaskListResponse(items=summaries, page=page, page_size=limit, total=total)


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: str, repo=Depends(get_task_repository)):
    """Retrieve a single task by id."""

    t = repo.get(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskDetail(
        task_id=t.get("task_id") or t.get("id"),
        title=t.get("title"),
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
        status=t.get("status"),
        last_step=t.get("last_step"),
        duration_sec=t.get("duration_sec"),
        thumb_url=t.get("thumb_url"),
        raw_path=t.get("raw_path"),
        mm_audio_path=t.get("mm_audio_path"),
        pack_path=t.get("pack_path"),
        created_at=t.get("created_at"),
        error_message=t.get("error_message"),
        error_reason=t.get("error_reason"),
    )


# Public exports for API and HTML routers
__all__ = ["router", "pages_router"]
