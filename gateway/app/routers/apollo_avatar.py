from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from gateway.app.deps import get_task_repository
from gateway.app.domain.apollo_avatar import ApolloAvatarRequest
from gateway.app.services.apollo_avatar_service import ApolloAvatarService
from gateway.app.task_repo_utils import normalize_task_payload
from gateway.app.utils.pipeline_config import pipeline_config_to_storage

router = APIRouter(prefix="/api/apollo/avatar", tags=["apollo-avatar"])


@router.post("/tasks")
def create_apollo_avatar_task(
    payload: ApolloAvatarRequest,
    repo=Depends(get_task_repository),
):
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
                {"apollo_avatar_target_duration_sec": str(payload.target_duration_sec)}
            ),
            "status": "pending",
            "last_step": None,
            "error_message": None,
            "meta": {
                "apollo_avatar": {
                    "target_duration_sec": payload.target_duration_sec,
                    "live_enabled": bool(payload.live_enabled),
                    "avatar_image_url": payload.avatar_image_url,
                    "reference_video_url": payload.reference_video_url,
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
        "target_duration_sec": payload.target_duration_sec,
        "live_enabled": bool(payload.live_enabled),
    }


@router.post("/{task_id}/generate")
async def generate_apollo_avatar(
    task_id: str,
    payload: ApolloAvatarRequest,
    repo=Depends(get_task_repository),
):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    live_enabled = bool(payload.live_enabled)
    service = ApolloAvatarService(repo=repo)
    artifacts = await service.generate_stitch_only(task, payload, live_enabled=live_enabled)
    repo.upsert(
        task_id,
        {
            "last_step": "apollo_avatar_generate",
            "status": "ready",
            "apollo_avatar_manifest_key": artifacts.manifest_url,
            "apollo_avatar_final_video_key": artifacts.final_video_url,
            "apollo_avatar": artifacts.model_dump(),
        },
    )
    return {
        "ok": True,
        "task_id": task_id,
        "segments": [s.model_dump() for s in artifacts.segments],
        "final_video_url": artifacts.final_video_url,
        "manifest_url": artifacts.manifest_url,
    }

