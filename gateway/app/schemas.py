from datetime import datetime
from typing import Optional

from pydantic import BaseModel, HttpUrl


class TaskCreate(BaseModel):
    source_url: HttpUrl
    platform: Optional[str] = None
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    video_type: Optional[str] = None
    template: Optional[str] = None
    title: Optional[str] = None
    note: Optional[str] = None


class TaskSummary(BaseModel):
    task_id: str
    title: Optional[str] = None
    platform: Optional[str] = None
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    video_type: Optional[str] = None
    template: Optional[str] = None
    status: str
    duration_sec: Optional[int] = None
    thumb_url: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True


class TaskDetail(TaskSummary):
    raw_path: Optional[str] = None
    mm_audio_path: Optional[str] = None
    pack_path: Optional[str] = None


class TaskListResponse(BaseModel):
    items: list[TaskSummary]
    page: int
    page_size: int
    total: int
