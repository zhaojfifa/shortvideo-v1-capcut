from datetime import datetime
import re
from typing import Optional

from pydantic import BaseModel, HttpUrl, validator

_URL_RE = re.compile(r"(https?://[^\s]+)")


class ParseRequest(BaseModel):
    task_id: str
    platform: str | None = None
    link: str

    @validator("link")
    def extract_first_url(cls, v: str) -> str:
        """Allow a full paste from social apps and keep only the first http/https URL."""

        m = _URL_RE.search(v)
        if not m:
            raise ValueError("No http/https URL found in link")
        url = m.group(1).rstrip("，。,.）)\"' ")
        return url


class SubtitlesRequest(BaseModel):
    task_id: str
    target_lang: str = "my"
    force: bool = False
    translate: bool = True
    with_scenes: bool = True


class DubRequest(BaseModel):
    task_id: str
    voice_id: str | None = None
    target_lang: str = "my"
    force: bool = False


class PackRequest(BaseModel):
    task_id: str


class TaskCreate(BaseModel):
    source_url: HttpUrl
    platform: Optional[str] = None
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    video_type: Optional[str] = None
    template: Optional[str] = None
    title: Optional[str] = None
    note: Optional[str] = None

    category_key: Optional[str] = "beauty"
    content_lang: Optional[str] = "my"
    ui_lang: Optional[str] = "en"
    style_preset: Optional[str] = None
    face_swap_enabled: Optional[bool] = False


class TaskSummary(BaseModel):
    task_id: str
    title: Optional[str] = None
    platform: Optional[str] = None
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    video_type: Optional[str] = None
    template: Optional[str] = None
    category_key: str
    content_lang: str
    ui_lang: str
    style_preset: Optional[str] = None
    face_swap_enabled: bool
    status: str
    last_step: Optional[str] = None
    duration_sec: Optional[int] = None
    thumb_url: Optional[str] = None
    created_at: datetime
    error_reason: Optional[str] = None
    error_message: Optional[str] = None

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
