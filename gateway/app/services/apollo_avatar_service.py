from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from gateway.app import config
from gateway.app.domain.apollo_avatar import ApolloAvatarRequest, GenArtifacts, SegmentPlan
from gateway.app.providers.fal_wan26_i2v import build_default_provider
from gateway.app.providers.video_gen_base import ProviderError

_DURATION_SECONDS = {"15s": 15, "30s": 30}


def validate_duration_profile(duration_profile: str) -> None:
    if duration_profile not in _DURATION_SECONDS:
        raise HTTPException(status_code=400, detail="duration_profile must be one of: 15s, 30s")


def build_segment_plan(duration_profile: str) -> SegmentPlan:
    validate_duration_profile(duration_profile)
    total_seconds = _DURATION_SECONDS[duration_profile]
    return SegmentPlan(
        segments_count=max(1, total_seconds // 5),
        segment_seconds=5,
        duration_profile=duration_profile,
    )


def _task_live_enabled(task: dict[str, Any]) -> bool:
    meta = task.get("meta")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    if not isinstance(meta, dict):
        return False
    if isinstance(meta.get("live_enabled"), bool):
        return bool(meta.get("live_enabled"))
    apollo_meta = meta.get("apollo_avatar")
    if isinstance(apollo_meta, dict):
        return bool(apollo_meta.get("live_enabled"))
    return False


def _to_demo_artifacts(*, task_id: str, duration_profile: str) -> GenArtifacts:
    output_name = "demo_output_30.mp4" if duration_profile == "30s" else "demo_output_15.mp4"
    return GenArtifacts(
        segments_keys=[],
        final_video_key=f"static/demo/{output_name}",
        manifest_key=f"deliver/apollo_avatar/{task_id}/manifest.demo.json",
        demo=True,
    )


def generate(task: dict[str, Any], req: ApolloAvatarRequest) -> GenArtifacts:
    validate_duration_profile(req.duration_profile)

    live_enabled = bool(config.settings.apollo_avatar_live_enabled) and _task_live_enabled(task)
    task_id = str(task.get("task_id") or task.get("id") or "")
    if not live_enabled:
        return _to_demo_artifacts(task_id=task_id, duration_profile=req.duration_profile)

    provider = build_default_provider()
    try:
        video_url = provider.generate_sync(
            image_url=req.avatar_image_key or "",
            prompt=req.prompt or "",
            duration_sec=_DURATION_SECONDS[req.duration_profile],
            resolution=config.WAN26_RESOLUTION,
            request_id=task_id,
        )
    except ProviderError:
        raise

    return GenArtifacts(
        segments_keys=[],
        final_video_key=video_url,
        manifest_key=f"deliver/apollo_avatar/{task_id}/manifest.json",
        demo=False,
    )

