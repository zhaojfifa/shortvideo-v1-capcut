from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from gateway.app.deps import get_task_repository
from gateway.app.domain.apollo_avatar import ApolloAvatarRequest
from gateway.app.services import apollo_avatar_service
from gateway.app.task_repo_utils import normalize_task_payload
from gateway.app.utils.pipeline_config import pipeline_config_to_storage

router = APIRouter(prefix="/api/apollo/avatar", tags=["apollo-avatar"])


@router.post("/tasks")
def create_apollo_avatar_task(
    payload: ApolloAvatarRequest,
    repo=Depends(get_task_repository),
):
    apollo_avatar_service.validate_duration_profile(payload.duration_profile)

    task_id = uuid4().hex[:12]
    task_payload = normalize_task_payload(
        {
            "task_id": task_id,
            "title": "ApolloAvatar",
            "source_url": None,
            "platform": "apollo_avatar",
            "category_key": "apollo_avatar",
            "content_lang": "mm",
            "ui_lang": "zh",
            "pipeline_config": pipeline_config_to_storage(
                {"apollo_avatar_duration_profile": payload.duration_profile}
            ),
            "status": "pending",
            "last_step": None,
            "error_message": None,
            "meta": {
                "apollo_avatar": {
                    "duration_profile": payload.duration_profile,
                    "live_enabled": bool(payload.live_enabled),
                    "avatar_image_key": payload.avatar_image_key,
                    "reference_video_key": payload.reference_video_key,
                    "prompt": payload.prompt,
                    "seed": payload.seed,
                }
            },
        },
        is_new=True,
    )
    repo.create(task_payload)
    stored = repo.get(task_id)
    if not stored:
        raise HTTPException(status_code=500, detail="task persistence failed")
    return {
        "ok": True,
        "task_id": task_id,
        "duration_profile": payload.duration_profile,
        "live_enabled": bool(payload.live_enabled),
    }


@router.post("/{task_id}/generate")
def generate_apollo_avatar(
    task_id: str,
    payload: ApolloAvatarRequest,
    repo=Depends(get_task_repository),
):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    artifacts = apollo_avatar_service.generate(task, payload)
    repo.upsert(
        task_id,
        {
            "last_step": "apollo_avatar_generate",
            "status": "ready",
            "apollo_avatar_manifest_key": artifacts.manifest_key,
            "apollo_avatar_final_video_key": artifacts.final_video_key,
        },
    )
    return {
        "ok": True,
        "task_id": task_id,
        "segments_keys": artifacts.segments_keys,
        "final_video_key": artifacts.final_video_key,
        "manifest_key": artifacts.manifest_key,
        "demo": artifacts.demo,
    }

