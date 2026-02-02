from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


DurationProfile = Literal["15s", "30s"]


class ApolloAvatarRequest(BaseModel):
    duration_profile: DurationProfile = "15s"
    live_enabled: bool = False
    avatar_image_key: str | None = None
    reference_video_key: str | None = None
    prompt: str | None = None
    seed: int | None = None


class SegmentPlan(BaseModel):
    segments_count: int
    segment_seconds: int = 5
    duration_profile: DurationProfile


class GenArtifacts(BaseModel):
    segments_keys: list[str]
    final_video_key: str
    manifest_key: str
    demo: bool = False

