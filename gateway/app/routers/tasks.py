from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models
from ..db import get_db
from ..schemas import TaskCreate, TaskDetail, TaskListResponse, TaskSummary

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


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


@router.post("", response_model=TaskDetail)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    """
    Create a Task record. Status defaults to pending; pipeline integration is handled later.
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
        status="pending",
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)

    return TaskDetail(
        task_id=db_task.id,
        title=db_task.title,
        platform=db_task.platform,
        account_id=db_task.account_id,
        account_name=db_task.account_name,
        video_type=db_task.video_type,
        template=db_task.template,
        status=db_task.status,
        duration_sec=db_task.duration_sec,
        thumb_url=db_task.thumb_url,
        raw_path=db_task.raw_path,
        mm_audio_path=db_task.mm_audio_path,
        pack_path=db_task.pack_path,
        created_at=db_task.created_at,
    )


@router.get("", response_model=TaskListResponse)
def list_tasks(
    db: Session = Depends(get_db),
    account_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    """
    List tasks with optional filtering by account or status.
    """

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
                status=t.status,
                duration_sec=t.duration_sec,
                thumb_url=t.thumb_url,
                created_at=t.created_at,
            )
        )

    return TaskListResponse(items=summaries, page=page, page_size=page_size, total=total)


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: str, db: Session = Depends(get_db)):
    """
    Retrieve a single task by id.
    """

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
        status=t.status,
        duration_sec=t.duration_sec,
        thumb_url=t.thumb_url,
        raw_path=t.raw_path,
        mm_audio_path=t.mm_audio_path,
        pack_path=t.pack_path,
        created_at=t.created_at,
    )
