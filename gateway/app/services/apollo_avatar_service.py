from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from gateway.app import config
from gateway.app.providers.fal_wan26_i2v import build_default_provider
from gateway.app.providers.video_gen_base import ProviderError

_DURATION_SECONDS = {
    "15s": 15,
    "30s": 30,
}


def _task_live_enabled(task: dict[str, Any]) -> bool:
    meta = task.get("meta")
    if isinstance(meta, str):
        try:
            import json

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


def _to_demo_artifacts(*, task_id: str, duration_profile: str) -> dict[str, Any]:
    output_name = "demo_output_30.mp4" if duration_profile == "30s" else "demo_output_15.mp4"
    return {
        "demo": True,
        "segments_keys": [],
        "final_video_key": f"static/demo/{output_name}",
        "manifest_key": f"deliver/apollo_avatar/{task_id}/manifest.demo.json",
    }


def generate(
    *,
    task: dict[str, Any],
    image_url: str,
    prompt: str,
    duration_profile: str,
    request_id: str,
) -> dict[str, Any]:
    if duration_profile not in _DURATION_SECONDS:
        raise HTTPException(status_code=400, detail="duration_profile must be one of: 15s, 30s")

    # Double billing gate: global env + per-task meta
    live_enabled = bool(config.settings.apollo_avatar_live_enabled) and _task_live_enabled(task)
    if not live_enabled:
        return _to_demo_artifacts(task_id=request_id, duration_profile=duration_profile)

    provider = build_default_provider()
    try:
        video_url = provider.generate_sync(
            image_url=image_url,
            prompt=prompt,
            duration_sec=_DURATION_SECONDS[duration_profile],
            resolution=config.WAN26_RESOLUTION,
            request_id=request_id,
        )
    except ProviderError:
        raise

    return {
        "demo": False,
        "segments_keys": [],
        "final_video_key": video_url,
        "manifest_key": f"deliver/apollo_avatar/{request_id}/manifest.json",
    }

