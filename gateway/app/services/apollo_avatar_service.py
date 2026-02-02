from __future__ import annotations

from fastapi import HTTPException

from gateway.app.config import get_settings
from gateway.app.domain.apollo_avatar import ApolloAvatarRequest, GenArtifacts, SegmentPlan

_DURATION_SECONDS = {"15s": 15, "30s": 30}


def validate_duration_profile(duration_profile: str) -> None:
    if duration_profile not in _DURATION_SECONDS:
        raise HTTPException(status_code=400, detail="duration_profile must be one of: 15s, 30s")


def build_segment_plan(duration_profile: str) -> SegmentPlan:
    validate_duration_profile(duration_profile)
    total_seconds = _DURATION_SECONDS[duration_profile]
    segments_count = max(1, total_seconds // 5)
    return SegmentPlan(
        segments_count=segments_count,
        segment_seconds=5,
        duration_profile=duration_profile,
    )


def _task_live_enabled(task: dict) -> bool:
    meta = task.get("meta")
    if not isinstance(meta, dict):
        return False
    apollo_avatar = meta.get("apollo_avatar")
    if not isinstance(apollo_avatar, dict):
        return False
    return bool(apollo_avatar.get("live_enabled"))


def enforce_live_gate(task: dict) -> None:
    settings = get_settings()
    if not settings.apollo_avatar_live_enabled:
        raise HTTPException(status_code=403, detail="Apollo Avatar live generation is disabled")
    if not _task_live_enabled(task):
        raise HTTPException(status_code=403, detail="Task is not enabled for Apollo Avatar live generation")


def generate(task: dict, req: ApolloAvatarRequest) -> GenArtifacts:
    enforce_live_gate(task)
    plan = build_segment_plan(req.duration_profile)
    task_id = str(task.get("task_id") or task.get("id") or "")
    segment_keys = [
        f"deliver/apollo_avatar/{task_id}/segments/seg_{i+1:02d}.mp4"
        for i in range(plan.segments_count)
    ]
    return GenArtifacts(
        segments_keys=segment_keys,
        final_video_key=f"deliver/apollo_avatar/{task_id}/output_{req.duration_profile}.mp4",
        manifest_key=f"deliver/apollo_avatar/{task_id}/manifest.json",
        demo=False,
    )

