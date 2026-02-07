from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, UploadFile, File, Form, Security
from fastapi.responses import JSONResponse
from typing import Optional, Any, Dict

from gateway.app.deps import get_task_repository
from gateway.app.domain.apollo_avatar import ApolloAvatarRequest
from gateway.app.services.apollo_avatar_assets import save_avatar_image, save_ref_video
from gateway.app.config import get_settings
from gateway.app.services.steps_v1 import (
    run_apollo_avatar_generate_step,
    run_post_generate_pipeline,
)
from gateway.app.services.status_policy.utils import policy_upsert
from gateway.app.services.task_events import append_task_event as _append_task_event
from gateway.app.task_repo_utils import normalize_task_payload
from gateway.app.utils.pipeline_config import pipeline_config_to_storage
from gateway.app.routers.tasks import api_key_header, _op_key_valid_value
from gateway.app.scenes.apollo_avatar.publish_hub import build_apollo_avatar_publish_hub

router = APIRouter(prefix="/api/apollo/avatar", tags=["apollo-avatar"])
logger = logging.getLogger(__name__)


def _policy_upsert(repo, task_id: str, updates: dict, *, task: dict | None = None, step: str = "router.apollo_avatar", force: bool = False):
    return policy_upsert(repo, task_id, task, updates, step=step, force=force)


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
            "kind": "apollo_avatar",
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
                "live": bool(live_enabled),
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
            "strategy": apollo_meta.get("strategy"),
        }
    )
    meta["apollo_avatar"] = apollo_meta
    meta["live"] = bool(live_enabled)
    _policy_upsert(repo, task_id, {"meta": meta})
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
    payload: Optional[Dict[str, Any]] = Body(default=None),
    repo=Depends(get_task_repository),
):
    try:
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
        live_requested = bool(payload.get("live")) if payload and "live" in payload else bool(
            (apollo_meta.get("live_enabled") if isinstance(apollo_meta, dict) else None)
            or (meta.get("live") if isinstance(meta, dict) else None)
        )
        logger.info(
            "ApolloAvatar generate request",
            extra={
                "task_id": task_id,
                "live": live_requested,
                "target_duration_sec": apollo_meta.get("target_duration_sec"),
            },
        )
        if live_requested and not bool(getattr(settings, "apollo_avatar_live_enabled", False)):
            _append_task_event(
                task,
                channel="apollo_avatar",
                code="generate.error",
                message="Live gate disabled",
                extra={"reason": "live_gate_disabled", "live": True},
            )
            _policy_upsert(repo, task_id, {"events": task.get("events") or []})
            raise HTTPException(status_code=403, detail="Live gate disabled")

        force = bool(payload.get("force")) if payload else False

        req = ApolloAvatarRequest(
            target_duration_sec=int(
                (payload.get("target_duration_sec") if payload else None)
                or apollo_meta.get("target_duration_sec")
                or 15
            ),
            prompt=str(
                (payload.get("prompt") if payload else None)
                or apollo_meta.get("prompt")
                or ""
            ),
            seed=(payload.get("seed") if payload else apollo_meta.get("seed")),
            avatar_image_url=str(
                (payload.get("avatar_image_url") if payload else None)
                or apollo_meta.get("avatar_image_url")
                or ""
            ),
            reference_video_url=str(
                (payload.get("reference_video_url") if payload else None)
                or apollo_meta.get("reference_video_url")
                or ""
            ),
            live_enabled=live_requested,
        )
        if live_requested and not bool(apollo_meta.get("live_enabled")):
            raise HTTPException(status_code=403, detail="Task is not enabled for live generation")

        if not req.avatar_image_url or not req.reference_video_url:
            raise HTTPException(status_code=400, detail="apollo_avatar assets missing: avatar/ref")

        resp = await run_apollo_avatar_generate_step(
            task=task,
            task_id=task_id,
            req=req,
            repo=repo,
            live_enabled=live_requested,
            force=force,
        )
        background_tasks.add_task(
            run_post_generate_pipeline,
            task_id=task_id,
            repo=repo,
            target_lang=(task.get("content_lang") or "my"),
            translate=True,
            force=False,
        )
        return resp
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("ApolloAvatar generate failed", extra={"task_id": task_id})
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "apollo_avatar_generate_failed",
                "message": str(exc),
                "task_id": task_id,
            },
        )


@router.get("/{task_id}/publish_hub")
def apollo_avatar_publish_hub(
    task_id: str,
    repo=Depends(get_task_repository),
    op_key: str | None = Security(api_key_header),
):
    if not _op_key_valid_value(op_key):
        raise HTTPException(status_code=401, detail="OP key required")
    task = repo.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return build_apollo_avatar_publish_hub(task)

