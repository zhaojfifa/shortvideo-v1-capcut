"""Pipeline orchestration to run parse → subtitles → dub → pack for a task."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from gateway.app.db import SessionLocal
from gateway.app.core.workspace import (
    Workspace,
    get_task_workspace,
    pack_zip_path,
    raw_path,
    relative_to_task_workspace,
    relative_to_workspace,
)
from gateway.app import models, schemas
from gateway.app.services.steps_v1 import (
    run_dub_step,
    run_pack_step,
    run_parse_step,
    run_subtitles_step,
)
logger = logging.getLogger(__name__)

DEFAULT_MM_LANG = os.getenv("DEFAULT_MM_LANG", "my")
DEFAULT_MM_VOICE_ID = os.getenv("DEFAULT_MM_VOICE_ID", "mm_female_1")


def run_pipeline_background(task_id: str):
    """Entry point for FastAPI BackgroundTasks; manages its own DB session."""

    db = SessionLocal()
    try:
        asyncio.run(run_pipeline_for_task(task_id, db))
    finally:
        db.close()


async def run_pipeline_for_task(task_id: str, db: Session):
    """Execute the V1 pipeline synchronously in sequence for the given task."""

    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        logger.error("Task %s not found, abort pipeline", task_id)
        return

    get_task_workspace(task_id)
    workspace = Workspace(task_id)

    logger.info(
        "Starting pipeline for task %s",
        task_id,
    )
    logger.info(
        "Pipeline context task=%s category=%s content_lang=%s ui_lang=%s video_type=%s face_swap_enabled=%s",
        task_id,
        getattr(task, "category_key", None),
        getattr(task, "content_lang", None),
        getattr(task, "ui_lang", None),
        getattr(task, "video_type", None),
        getattr(task, "face_swap_enabled", None),
    )
    task.status = "processing"
    task.last_step = None
    task.error_message = None
    task.error_reason = None
    db.commit()

    async def _run_step(name: str, coro):
        try:
            result = await coro
            task.last_step = name
            db.commit()
            return True, result
        except HTTPException as exc:
            logger.exception("%s step failed for task %s: %s", name, task_id, exc)
            return False, exc.detail or str(exc)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("%s step failed for task %s", name, task_id)
            return False, str(exc)

    # Parse
    parse_req = schemas.ParseRequest(
        task_id=task.id,
        platform=task.platform,
        link=task.source_url,
    )
    ok, parse_res = await _run_step("parse", run_parse_step(parse_req))
    if not ok:
        task.status = "error"
        task.last_step = "parse"
        task.error_message = str(parse_res)
        task.error_reason = str(parse_res)
        task.updated_at = datetime.utcnow()
        db.commit()
        return

    raw_file = raw_path(task.id)
    if raw_file.exists():
        task.raw_path = relative_to_task_workspace(raw_file, task.id)
    if isinstance(parse_res, dict):
        duration_sec = parse_res.get("duration_sec")
    else:
        duration_sec = getattr(parse_res, "duration_sec", None)
    if duration_sec:
        task.duration_sec = int(duration_sec)
    db.commit()

    # Subtitles
    subs_req = schemas.SubtitlesRequest(
        task_id=task.id,
        target_lang=DEFAULT_MM_LANG,
        force=False,
        translate=True,
        with_scenes=True,
    )
    ok, subs_res = await _run_step("subtitles", run_subtitles_step(subs_req))
    if not ok:
        task.status = "error"
        task.last_step = "subtitles"
        task.error_message = str(subs_res)
        task.error_reason = str(subs_res)
        task.updated_at = datetime.utcnow()
        db.commit()
        return

    # Dub
    dub_req = schemas.DubRequest(
        task_id=task.id,
        voice_id=DEFAULT_MM_VOICE_ID,
        target_lang=DEFAULT_MM_LANG,
        force=False,
    )
    ok, dub_res = await _run_step("dub", run_dub_step(dub_req))
    if not ok:
        task.status = "error"
        task.last_step = "dub"
        task.error_message = str(dub_res)
        task.error_reason = str(dub_res)
        task.updated_at = datetime.utcnow()
        db.commit()
        return

    if workspace.mm_audio_exists():
        task.mm_audio_path = relative_to_task_workspace(workspace.mm_audio_path, task.id)
    elif isinstance(dub_res, dict):
        audio_path_val = dub_res.get("audio_path") or dub_res.get("path")
        if audio_path_val:
            task.mm_audio_path = str(audio_path_val)
    db.commit()

    # Pack
    pack_req = schemas.PackRequest(task_id=task.id)
    ok, pack_res = await _run_step("pack", run_pack_step(pack_req))
    if not ok:
        task.status = "error"
        task.last_step = "pack"
        task.error_message = str(pack_res)
        task.error_reason = str(pack_res)
        task.updated_at = datetime.utcnow()
        db.commit()
        return

    pack_file = pack_zip_path(task.id)
    if pack_file.exists():
        task.pack_path = relative_to_workspace(pack_file)
    elif isinstance(pack_res, dict):
        maybe_pack = pack_res.get("pack_path") or pack_res.get("zip_path")
        if maybe_pack:
            task.pack_path = str(maybe_pack)

    task.status = "ready"
    task.last_step = "pack"
    task.error_message = None
    task.error_reason = None
    task.updated_at = datetime.utcnow()
    db.commit()
    logger.info("Pipeline finished for task %s", task_id)
