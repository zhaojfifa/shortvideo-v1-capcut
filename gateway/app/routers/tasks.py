"""Task API and HTML routers for the gateway application."""

from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..schemas import TaskCreate, TaskDetail, TaskListResponse, TaskSummary
from ..services.pipeline_v1 import run_pipeline_background


BASE_DIR = Path(__file__).resolve().parents[1]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

pages_router = APIRouter()
api_router = APIRouter(prefix="/api", tags=["tasks"])


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
    request: Request, db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=500)
):
    """Render the task board HTML page."""

    db_tasks = (
        db.query(models.Task).order_by(models.Task.created_at.desc()).limit(limit).all()
    )

    rows: list[dict] = []
    for t in db_tasks:
        rows.append(
            {
                "task_id": t.id,
                "platform": t.platform,
                "source_url": t.source_url,
                "title": t.title or "",
                "category_key": t.category_key or "",
                "content_lang": t.content_lang or "",
                "status": t.status or "pending",
                "created_at": t.created_at.isoformat() if t.created_at else "",
                "pack_path": str(t.pack_path) if t.pack_path else None,
                "ui_lang": t.ui_lang or "",
            }
        )

    return templates.TemplateResponse(
        "tasks.html",
        {"request": request, "tasks": rows},
    )


@pages_router.get("/tasks/new", response_class=HTMLResponse)
async def tasks_new(request: Request) -> HTMLResponse:
    """Render suitcase quick-create page."""

    return templates.TemplateResponse(
        "tasks_new.html",
        {"request": request},
    )


@api_router.post("/tasks", response_model=TaskDetail)
def create_task(
    payload: TaskCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """Create a Task record and kick off the V1 pipeline asynchronously."""

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
        created_at=db_task.created_at,
        error_message=db_task.error_message,
        error_reason=db_task.error_reason,
    )


@api_router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    db: Session = Depends(get_db),
    account_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500, alias="limit"),
):
    """List tasks with optional filtering by account or status."""

    query = db.query(models.Task)

    if account_id:
        query = query.filter(models.Task.account_id == account_id)
    if status:
        query = query.filter(models.Task.status == status)

    total = query.count()
    items = (
        query.order_by(models.Task.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
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
                created_at=t.created_at,
                error_message=t.error_message,
                error_reason=t.error_reason,
            )
        )

    return TaskListResponse(items=summaries, page=page, page_size=page_size, total=total)


@api_router.get("/tasks/{task_id}", response_model=TaskDetail)
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
        created_at=t.created_at,
        error_message=t.error_message,
        error_reason=t.error_reason,
    )


# Backwards-compatible export for existing imports
router = api_router

__all__ = ["api_router", "pages_router", "router"]
