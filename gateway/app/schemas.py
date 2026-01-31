from datetime import datetime
import re
from typing import Literal, Optional

from pydantic import BaseModel, constr, root_validator, validator

_URL_RE = re.compile(r"(https?://[^\s]+)")


class ParseRequest(BaseModel):
    task_id: str
    platform: str | None = None
    link: str

    @root_validator(pre=True)
    def normalize_link(cls, values: dict) -> dict:
        link = values.get("link")
        if not link:
            for key in ("url", "source_url", "text"):
                candidate = values.get(key)
                if candidate:
                    values["link"] = candidate
                    break
        return values

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
    mm_text: Optional[str] = None


class PackRequest(BaseModel):
    task_id: str


class PublishRequest(BaseModel):
    task_id: str
    provider: Optional[Literal["r2", "local"]] = None
    force: bool = False


class PublishResponse(BaseModel):
    task_id: str
    provider: str
    publish_key: str
    download_url: str
    published_at: str


class TaskCreate(BaseModel):
    source_url: constr(strip_whitespace=True, min_length=1)
    platform: Optional[str] = None
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    video_type: Optional[str] = None
    template: Optional[str] = None
    title: Optional[str] = None
    note: Optional[str] = None
    selected_tool_ids: Optional[list[str]] = None
    pipeline_config: Optional[dict[str, str]] = None

    category_key: Optional[str] = "beauty"
    content_lang: Optional[str] = "my"
    ui_lang: Optional[str] = "en"
    style_preset: Optional[str] = None
    face_swap_enabled: Optional[bool] = False


class TaskUpdate(BaseModel):
    selected_tool_ids: Optional[list[str]] = None
    pipeline_config: Optional[dict[str, str]] = None


class TaskSummary(BaseModel):
    task_id: str
    title: Optional[str] = None
    source_url: Optional[str] = None
    source_link_url: Optional[str] = None
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
    pack_path: Optional[str] = None
    scenes_path: Optional[str] = None
    scenes_status: Optional[str] = None
    scenes_key: Optional[str] = None
    scenes_error: Optional[str] = None
    subtitles_status: Optional[str] = None
    subtitles_key: Optional[str] = None
    subtitles_error: Optional[str] = None
    dub_status: Optional[str] = None
    dub_error: Optional[str] = None
    pack_status: Optional[str] = None
    pack_error: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    error_reason: Optional[str] = None
    error_message: Optional[str] = None
    parse_provider: Optional[str] = None
    subtitles_provider: Optional[str] = None
    dub_provider: Optional[str] = None
    pack_provider: Optional[str] = None
    face_swap_provider: Optional[str] = None
    publish_status: Optional[str] = None
    publish_provider: Optional[str] = None
    publish_key: Optional[str] = None
    publish_url: Optional[str] = None
    published_at: Optional[str] = None
    priority: Optional[int] = None
    assignee: Optional[str] = None
    ops_notes: Optional[str] = None
    selected_tool_ids: Optional[list[str]] = None
    pipeline_config: Optional[dict[str, str]] = None

    class Config:
        orm_mode = True


class TaskDetail(TaskSummary):
    raw_path: Optional[str] = None
    origin_srt_path: Optional[str] = None
    mm_srt_path: Optional[str] = None
    mm_txt_path: Optional[str] = None
    mm_audio_path: Optional[str] = None
    mm_audio_key: Optional[str] = None
    pack_path: Optional[str] = None
    scenes_path: Optional[str] = None
    selected_tool_ids: Optional[list[str]] = None
    pipeline_config: Optional[dict[str, str]] = None
    stale: Optional[bool] = None
    stale_reason: Optional[str] = None
    stale_for_seconds: Optional[int] = None
    no_dub: Optional[bool] = None
    dub_skip_reason: Optional[str] = None
    subtitle_track_kind: Optional[str] = None


class DubResponse(TaskDetail):
    resolved_voice_id: Optional[str] = None
    resolved_edge_voice: Optional[str] = None
    audio_sha256: Optional[str] = None
    mm_audio_key: Optional[str] = None


class TaskListResponse(BaseModel):
    items: list[TaskSummary]
    page: int
    page_size: int
    total: int
