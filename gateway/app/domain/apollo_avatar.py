from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class SegmentSpec(BaseModel):
    idx: int
    duration_sec: int
    seed: Optional[int] = None


class SegmentPlan(BaseModel):
    target_duration_sec: Literal[15, 30]
    segment_duration_sec: Literal[5, 10]
    segment_count: Literal[3]
    segments: List[SegmentSpec]


class SegmentArtifact(BaseModel):
    idx: int
    duration_sec: int
    video_url: str
    request_id: str
    seed_used: Optional[int] = None


class GenArtifacts(BaseModel):
    provider: str
    plan: SegmentPlan
    segments: List[SegmentArtifact] = Field(default_factory=list)
    final_video_url: Optional[str] = None
    manifest_url: Optional[str] = None


class ApolloAvatarRequest(BaseModel):
    target_duration_sec: Literal[15, 30] = 15
    prompt: str
    seed: Optional[int] = None
    avatar_image_url: str
    reference_video_url: Optional[str] = None
    live_enabled: bool = False
