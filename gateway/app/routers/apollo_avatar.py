from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form

from gateway.app.deps import get_task_repository
from gateway.app.domain.apollo_avatar import ApolloAvatarRequest
from gateway.app.services.apollo_avatar_assets import save_avatar_image, save_ref_video
from gateway.app.config import get_settings
from gateway.app.services.steps_v1 import (
    append_task_event,
    run_apollo_avatar_generate_step,
    run_post_generate_pipeline,
)
from gateway.app.task_repo_utils import normalize_task_payload
from gateway.app.utils.pipeline_config import pipeline_config_to_storage

router = APIRouter(prefix="/api/apollo/avatar", tags=["apollo-avatar"])


@router.post("/tasks")
async def create_apollo_avatar_task(
    avatar_file: UploadFile = File(...),
    ref_video_file: UploadFile = File(...),
    duration_sec: int = Form(...),
    prompt: str = Form(...),
    seed: int | None = Form(default=None),
    live_enabled: bool = Form(default=False),
    repo=Depends(get_task_repository),
):
    if duration_sec not in (15, 30):
        raise HTTPException(status_code=400, detail="duration_sec must be 15 or 30")
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
                {"apollo_avatar_target_duration_sec": str(duration_sec)}
            ),
            "status": "pending",
            "last_step": None,
            "error_message": None,
            "meta": {
                "apollo_avatar": {
                    "target_duration_sec": duration_sec,
                    "live_enabled": bool(live_enabled),
                    "avatar_image_url": "",
                    "reference_video_url": "",
                    "prompt": prompt,
                    "seed": seed,
                }
            },
        },
        is_new=True,
    )
    repo.create(task_payload)
    stored = repo.get(task_id)
    if not stored:
        raise HTTPException(status_code=500, detail="task persistence failed")

    avatar_url = await save_avatar_image(stored, avatar_file)
    ref_url = await save_ref_video(stored, ref_video_file)
    meta = stored.get("meta") or {}
    if isinstance(meta, str):
        try:
            import json

            meta = json.loads(meta)
        except Exception:
            meta = {}
    apollo_meta = meta.get("apollo_avatar") if isinstance(meta, dict) else {}
    if not isinstance(apollo_meta, dict):
        apollo_meta = {}
    apollo_meta.update(
        {
            "avatar_image_url": avatar_url,
            "reference_video_url": ref_url,
            "target_duration_sec": duration_sec,
            "live_enabled": bool(live_enabled),
            "prompt": prompt,
            "seed": seed,
        }
    )
    meta["apollo_avatar"] = apollo_meta
    repo.upsert(task_id, {"meta": meta})
    return {
        "ok": True,
        "task_id": task_id,
        "target_duration_sec": duration_sec,
        "live_enabled": bool(live_enabled),
    }


@router.post("/{task_id}/generate")
async def generate_apollo_avatar(
    task_id: str,
    background_tasks: BackgroundTasks,
    payload: ApolloAvatarRequest | None = None,
    repo=Depends(get_task_repository),
):
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    meta = task.get("meta") or {}
    if isinstance(meta, str):
        try:
            import json

            meta = json.loads(meta)
        except Exception:
            meta = {}
    apollo_meta = meta.get("apollo_avatar") if isinstance(meta, dict) else {}
    if not isinstance(apollo_meta, dict):
        apollo_meta = {}
    settings = get_settings()
    live_enabled = bool(payload.live_enabled) if payload else bool(apollo_meta.get("live_enabled"))
    if live_enabled and not bool(getattr(settings, "apollo_avatar_live_enabled", False)):
        raise HTTPException(status_code=403, detail="Apollo Avatar live generation is disabled")

    req = payload or ApolloAvatarRequest(
        target_duration_sec=int(apollo_meta.get("target_duration_sec") or 15),
        prompt=str(apollo_meta.get("prompt") or ""),
        seed=apollo_meta.get("seed"),
        avatar_image_url=str(apollo_meta.get("avatar_image_url") or ""),
        reference_video_url=str(apollo_meta.get("reference_video_url") or ""),
        live_enabled=live_enabled,
    )
    if live_enabled and not bool(apollo_meta.get("live_enabled")):
        raise HTTPException(status_code=403, detail="Task is not enabled for live generation")

    resp = await run_apollo_avatar_generate_step(
        task=task,
        task_id=task_id,
        req=req,
        repo=repo,
        live_enabled=live_enabled,
    )
    append_task_event(repo, task_id, "pipeline", "AVATAR_POST_PIPELINE_START")
    background_tasks.add_task(
        run_post_generate_pipeline,
        task_id=task_id,
        repo=repo,
        target_lang=(task.get("content_lang") or "my"),
        translate=True,
        force=False,
    )
    return resp

