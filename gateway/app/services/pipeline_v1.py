"""Pipeline orchestration to run parse → subtitles → dub → pack for a task."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

from sqlalchemy.orm import Session

from gateway.app.db import SessionLocal
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

    logger.info("Starting pipeline for task %s", task_id)
    task.status = "processing"
    db.commit()

    try:
        # Parse
        parse_req = schemas.ParseRequest(
            task_id=task.id,
            platform=task.platform,
            link=task.source_url,
        )
        parse_res = await run_parse_step(parse_req)
        if isinstance(parse_res, dict):
            raw_path_val = parse_res.get("raw_path") or parse_res.get("raw")
            duration_sec = parse_res.get("duration_sec")
        else:
            raw_path_val = getattr(parse_res, "raw_path", None)
            duration_sec = getattr(parse_res, "duration_sec", None)

        if raw_path_val:
            task.raw_path = str(raw_path_val)
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
        await run_subtitles_step(subs_req)

        # Dub
        dub_req = schemas.DubRequest(
            task_id=task.id,
            voice_id=DEFAULT_MM_VOICE_ID,
            target_lang=DEFAULT_MM_LANG,
            force=False,
        )
        dub_res = await run_dub_step(dub_req)
        if isinstance(dub_res, dict):
            audio_path_val = (
                dub_res.get("audio_path")
                or dub_res.get("path")
                or dub_res.get("audio_mm_url")
            )
        else:
            audio_path_val = getattr(dub_res, "audio_path", None)
        if audio_path_val:
            task.mm_audio_path = str(audio_path_val)
        db.commit()

        # Pack
        pack_req = schemas.PackRequest(task_id=task.id)
        pack_res = await run_pack_step(pack_req)
        if isinstance(pack_res, dict):
            pack_path_val = pack_res.get("pack_path") or pack_res.get("zip_path")
        else:
            pack_path_val = getattr(pack_res, "pack_path", None)
        if pack_path_val:
            task.pack_path = str(pack_path_val)

        task.status = "ready"
        task.updated_at = datetime.utcnow()
        db.commit()
        logger.info("Pipeline finished for task %s", task_id)

    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline failed for task %s: %s", task_id, exc)
        task.status = "error"
        task.updated_at = datetime.utcnow()
        db.commit()
