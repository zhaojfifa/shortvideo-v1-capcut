"""Task API router and simple HTML task board page."""

import asyncio
from pathlib import Path
import re
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from gateway.app import models
from gateway.app.config import get_settings
from gateway.app.core.features import get_features
from gateway.app.core.workspace import (
    Workspace,
    origin_srt_path,
    pack_zip_path,
    relative_to_workspace,
    translated_srt_path,
    workspace_root,
)
from gateway.app.db import get_db
from gateway.app.web.templates import get_templates
from gateway.app.schemas import (
    PackRequest,
    ParseRequest,
    SubtitlesRequest,
    TaskCreate,
    TaskDetail,
    TaskListResponse,
    TaskSummary,
)
from gateway.app.services.artifact_storage import object_exists
from gateway.app.services.scene_split import enqueue_scenes_build
from gateway.app.services.publish_service import publish_task_pack, resolve_download_url
from gateway.app.steps.pipeline_v1 import run_pipeline_background
from gateway.app.services.steps_v1 import (
    run_pack_step as run_pack_step_v1,
    run_parse_step as run_parse_step_v1,
    run_subtitles_step as run_subtitles_step_v1,
)

router = APIRouter(prefix="/tasks")
pages_router = APIRouter()

templates = get_templates()


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
    request: Request, db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=500)
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
    request: Request, db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=500)
):
    response = await tasks_board_page(request, db=db, limit=limit)
    response.context["is_mobile"] = True
    response.context["view"] = "mobile"
    return response


@pages_router.get("/m/tasks/new", response_class=HTMLResponse)
async def tasks_new_mobile(request: Request) -> HTMLResponse:
    response = await tasks_new(request)
    response.context["is_mobile"] = True
    response.context["view"] = "mobile"
    return response


def _resolve_paths(task: models.Task) -> dict[str, Optional[str]]:
    workspace = Workspace(task.id)
    raw_video = task.raw_path or None
    if not raw_video and workspace.raw.exists():
        raw_video = relative_to_workspace(workspace.raw)

    origin_srt = getattr(task, "origin_srt_path", None)
    mm_srt = getattr(task, "mm_srt_path", None)
    if not origin_srt:
        path = origin_srt_path(task.id)
        if path.exists():
            origin_srt = relative_to_workspace(path)
    if not mm_srt:
        path = translated_srt_path(task.id, "mm")
        if path.exists():
            mm_srt = relative_to_workspace(path)

    mm_audio = getattr(task, "mm_audio_path", None) or None
    if not mm_audio and workspace.mm_audio_exists():
        mm_audio = relative_to_workspace(workspace.mm_audio_path)

    pack_path = task.pack_path or None
    if not pack_path:
        pack = pack_zip_path(task.id)
        if pack.exists():
            pack_path = relative_to_workspace(pack)

    scenes_path = getattr(task, "scenes_key", None) or None
    if not scenes_path:
        candidate = workspace_root() / "deliver" / "scenes" / task.id / "scenes.zip"
        if candidate.exists():
            scenes_path = relative_to_workspace(candidate)

    return {
        "raw_path": raw_video,
        "origin_srt_path": origin_srt,
        "mm_srt_path": mm_srt,
        "mm_audio_path": mm_audio,
        "pack_path": pack_path,
        "scenes_path": scenes_path,
    }


def _extract_first_http_url(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"https?://\\S+", text)
    return match.group(0) if match else None


@pages_router.get("/tasks/{task_id}", response_class=HTMLResponse)
async def task_workbench_page(
    request: Request, task_id: str, db: Session = Depends(get_db)
) -> HTMLResponse:
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        return templates.TemplateResponse(
            "task_not_found.html",
            {"request": request, "task_id": task_id},
            status_code=404,
        )

    paths = _resolve_paths(task)
    task_json = {
        "task_id": task.id,
        "status": task.status,
        "platform": task.platform,
        "category_key": task.category_key,
        "content_lang": task.content_lang,
        "ui_lang": task.ui_lang,
        "source_url": task.source_url,
        "raw_path": paths["raw_path"],
        "origin_srt_path": paths["origin_srt_path"],
        "mm_srt_path": paths["mm_srt_path"],
        "mm_audio_path": paths["mm_audio_path"],
        "pack_path": paths["pack_path"],
        "scenes_path": paths["scenes_path"],
        "scenes_status": getattr(task, "scenes_status", None),
        "scenes_key": getattr(task, "scenes_key", None),
        "scenes_error": getattr(task, "scenes_error", None),
        "subtitles_status": getattr(task, "subtitles_status", None),
        "subtitles_key": getattr(task, "subtitles_key", None),
        "subtitles_error": getattr(task, "subtitles_error", None),
    }
    task_view = {"source_url_open": _extract_first_http_url(task.source_url)}

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
    request: Request, task_id: str, db: Session = Depends(get_db)
) -> HTMLResponse:
    response = await task_workbench_page(request, task_id=task_id, db=db)
    response.context["is_mobile"] = True
    response.context["view"] = "mobile"
    return response


@router.post("", response_model=TaskDetail)
def create_task(
    payload: TaskCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """
    Create a Task record and kick off the V1 pipeline asynchronously.
    """

    platform = payload.platform or _infer_platform_from_url(str(payload.source_url))
    task_id = uuid4().hex[:12]

    db_task = models.Task(
        id=task_id,
        title=payload.title,
        source_url=str(payload.source_url),
        platform=platform,
        account_id=payload.account_id,
        account_name=payload.account_name,
        video_type=payload.video_type,
        template=payload.template,
        category_key=payload.category_key or "beauty",
        content_lang=payload.content_lang or "my",
        ui_lang=payload.ui_lang or "en",
        style_preset=payload.style_preset,
        face_swap_enabled=bool(payload.face_swap_enabled),
        status="pending",
        last_step=None,
        error_message=None,
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)

    background_tasks.add_task(run_pipeline_background, db_task.id)

    return TaskDetail(
        task_id=db_task.id,
        title=db_task.title,
        platform=db_task.platform,
        account_id=db_task.account_id,
        account_name=db_task.account_name,
        video_type=db_task.video_type,
        template=db_task.template,
        category_key=db_task.category_key or "beauty",
        content_lang=db_task.content_lang or "my",
        ui_lang=db_task.ui_lang or "en",
        style_preset=db_task.style_preset,
        face_swap_enabled=bool(db_task.face_swap_enabled),
        status=db_task.status,
        last_step=db_task.last_step,
        duration_sec=db_task.duration_sec,
        thumb_url=db_task.thumb_url,
        raw_path=db_task.raw_path,
        mm_audio_path=db_task.mm_audio_path,
        pack_path=db_task.pack_path,
        scenes_path=db_task.scenes_key,
        scenes_status=db_task.scenes_status,
        scenes_key=db_task.scenes_key,
        scenes_error=db_task.scenes_error,
        subtitles_status=db_task.subtitles_status,
        subtitles_key=db_task.subtitles_key,
        subtitles_error=db_task.subtitles_error,
        created_at=db_task.created_at,
        updated_at=db_task.updated_at,
        error_message=db_task.error_message,
        error_reason=db_task.error_reason,
    )


@router.get("", response_model=TaskListResponse)
def list_tasks(
    db: Session = Depends(get_db),
    account_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=500),
):
    """
    List tasks ordered by creation time (newest first) with an adjustable limit.
    """

    query = db.query(models.Task)

    if account_id:
        query = query.filter(models.Task.account_id == account_id)
    if status:
        query = query.filter(models.Task.status == status)

    total = query.count()
    items = (
        query.order_by(models.Task.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    summaries: list[TaskSummary] = []
    for t in items:
        summaries.append(
            TaskSummary(
                task_id=t.id,
                title=t.title,
                platform=t.platform,
                account_id=t.account_id,
                account_name=t.account_name,
                video_type=t.video_type,
                template=t.template,
                category_key=t.category_key or "beauty",
                content_lang=t.content_lang or "my",
                ui_lang=t.ui_lang or "en",
                style_preset=t.style_preset,
                face_swap_enabled=bool(t.face_swap_enabled),
                status=t.status,
                last_step=t.last_step,
                duration_sec=t.duration_sec,
                thumb_url=t.thumb_url,
                pack_path=t.pack_path,
                scenes_path=t.scenes_key,
                scenes_status=t.scenes_status,
                scenes_key=t.scenes_key,
                scenes_error=t.scenes_error,
                subtitles_status=t.subtitles_status,
                subtitles_key=t.subtitles_key,
                subtitles_error=t.subtitles_error,
                created_at=t.created_at,
                updated_at=t.updated_at,
                error_message=t.error_message,
                error_reason=t.error_reason,
            )
        )

    return TaskListResponse(items=summaries, page=page, page_size=limit, total=total)


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: str, db: Session = Depends(get_db)):
    """Retrieve a single task by id."""

    t = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskDetail(
        task_id=t.id,
        title=t.title,
        platform=t.platform,
        account_id=t.account_id,
        account_name=t.account_name,
        video_type=t.video_type,
        template=t.template,
        category_key=t.category_key or "beauty",
        content_lang=t.content_lang or "my",
        ui_lang=t.ui_lang or "en",
        style_preset=t.style_preset,
        face_swap_enabled=bool(t.face_swap_enabled),
        status=t.status,
        last_step=t.last_step,
        duration_sec=t.duration_sec,
        thumb_url=t.thumb_url,
        raw_path=t.raw_path,
        mm_audio_path=t.mm_audio_path,
        pack_path=t.pack_path,
        scenes_path=t.scenes_key,
        scenes_status=t.scenes_status,
        scenes_key=t.scenes_key,
        scenes_error=t.scenes_error,
        subtitles_status=t.subtitles_status,
        subtitles_key=t.subtitles_key,
        subtitles_error=t.subtitles_error,
        created_at=t.created_at,
        updated_at=t.updated_at,
        error_message=t.error_message,
        error_reason=t.error_reason,
    )


@router.post("/{task_id}/parse")
def build_parse(
    task_id: str,
    payload: ParseTaskRequest | None = None,
    db: Session = Depends(get_db),
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    link = task.source_url or ""
    if not link:
        raise HTTPException(status_code=400, detail="source_url is empty; cannot parse")

    platform = (payload.platform if payload else None) or task.platform
    task.last_step = "parse"
    task.status = "processing"
    db.commit()

    req = ParseRequest(task_id=task_id, platform=platform, link=link)
    try:
        asyncio.run(run_parse_step_v1(req))
    except HTTPException as exc:
        task.last_step = "parse"
        task.status = "failed"
        task.error_message = str(exc.detail)
        task.error_reason = "parse_failed"
        db.commit()
        raise

    db.refresh(task)
    return get_task(task_id, db)


@router.post("/{task_id}/scenes")
def build_scenes(
    task_id: str,
    background_tasks: BackgroundTasks,
    payload: ScenesRequest | None = None,
    db: Session = Depends(get_db),
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    def _update(task_id: str, fields: dict) -> None:
        t = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not t:
            return
        for key, value in fields.items():
            if hasattr(t, key):
                setattr(t, key, value)
        db.commit()

    return enqueue_scenes_build(
        task_id,
        task=task,
        object_exists=object_exists,
        update_task=_update,
        background_tasks=background_tasks,
    )


@router.post("/{task_id}/subtitles")
def build_subtitles(
    task_id: str,
    payload: SubtitlesTaskRequest | None = None,
    db: Session = Depends(get_db),
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.subtitles_status == "ready" and task.subtitles_key:
        return {
            "task_id": task_id,
            "status": "already_ready",
            "subtitles_key": task.subtitles_key,
            "message": "Subtitles already ready",
            "error": None,
        }

    target_lang = (payload.target_lang if payload else None) or task.content_lang or "my"
    force = payload.force if payload else False
    translate = payload.translate if payload else True

    subs_req = SubtitlesRequest(
        task_id=task_id,
        target_lang=target_lang,
        force=force,
        translate=translate,
        with_scenes=True,
    )
    try:
        asyncio.run(run_subtitles_step_v1(subs_req))
    except HTTPException as exc:
        task.subtitles_status = "error"
        task.subtitles_error = str(exc.detail)
        db.commit()
        raise

    db.refresh(task)
    return TaskDetail(
        task_id=task.id,
        title=task.title,
        platform=task.platform,
        account_id=task.account_id,
        account_name=task.account_name,
        video_type=task.video_type,
        template=task.template,
        category_key=task.category_key or "beauty",
        content_lang=task.content_lang or "my",
        ui_lang=task.ui_lang or "en",
        style_preset=task.style_preset,
        face_swap_enabled=bool(task.face_swap_enabled),
        status=task.status,
        last_step=task.last_step,
        duration_sec=task.duration_sec,
        thumb_url=task.thumb_url,
        raw_path=task.raw_path,
        mm_audio_path=task.mm_audio_path,
        pack_path=task.pack_path,
        scenes_path=task.scenes_key,
        scenes_status=task.scenes_status,
        scenes_key=task.scenes_key,
        scenes_error=task.scenes_error,
        created_at=task.created_at,
        updated_at=task.updated_at,
        error_message=task.error_message,
        error_reason=task.error_reason,
    )


@router.post("/{task_id}/pack")
def build_pack(
    task_id: str,
    db: Session = Depends(get_db),
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    task.last_step = "pack"
    task.status = "processing"
    db.commit()

    try:
        asyncio.run(run_pack_step_v1(PackRequest(task_id=task_id)))
    except HTTPException as exc:
        task.last_step = "pack"
        task.status = "failed"
        task.error_message = str(exc.detail)
        task.error_reason = "pack_failed"
        db.commit()
        raise

    db.refresh(task)
    return get_task(task_id, db)


@router.post("/{task_id}/publish")
def publish_task(
    task_id: str,
    payload: PublishTaskRequest | None = None,
    db: Session = Depends(get_db),
):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    res = publish_task_pack(
        task_id,
        db,
        provider=(payload.provider if payload else None),
        force=(payload.force if payload else False),
    )
    download_url = res.get("download_url") or resolve_download_url(task)
    return {
        "task_id": task_id,
        "provider": res.get("provider"),
        "publish_key": res.get("publish_key"),
        "download_url": download_url,
        "published_at": res.get("published_at"),
    }


# Public exports for API and HTML routers
__all__ = ["router", "pages_router"]
