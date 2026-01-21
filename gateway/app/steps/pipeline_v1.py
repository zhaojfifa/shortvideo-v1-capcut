"""Pipeline orchestration to run parse → subtitles → dub → pack for a task."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from gateway.app.config import get_settings
from gateway.app.db import SessionLocal, engine
from gateway.app.core.workspace import (
    Workspace,
    get_task_workspace,
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
from gateway.app.providers.registry import get_provider, resolve_tool_providers
from gateway.app.utils.pipeline_config import parse_pipeline_config
logger = logging.getLogger(__name__)

DEFAULT_MM_LANG = os.getenv("DEFAULT_MM_LANG", "my")
DEFAULT_MM_VOICE_ID = os.getenv("DEFAULT_MM_VOICE_ID", "mm_female_1")


def get_defaults() -> dict:
    settings = get_settings()
    tools = resolve_tool_providers(engine, settings).get("tools", {})
    return {tool: config.get("provider") for tool, config in tools.items()}


def run_pipeline_background(task_id: str):
    """Entry point for FastAPI BackgroundTasks; manages its own DB session."""

    db = SessionLocal()
    try:
        asyncio.run(run_pipeline_for_task(task_id, db))
    except Exception as exc:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if task:
            task.status = "error"
            task.last_step = "pipeline"
            task.error_reason = "pipeline_crash"
            task.error_message = str(exc)
            task.updated_at = datetime.utcnow()
            db.commit()
        logger.exception("Pipeline crashed for task %s", task_id)
    finally:
        db.close()


async def run_pipeline_for_task(task_id: str, db: Session):
    """Execute the V1 pipeline synchronously in sequence for the given task."""

    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        logger.error("Task %s not found, abort pipeline", task_id)
        return

    try:
        settings = get_settings()
        tool_cfg = resolve_tool_providers(engine, settings).get("tools", {})
        defaults = {
            key: (value.get("provider") if isinstance(value, dict) else None)
            for key, value in tool_cfg.items()
        }
        enabled = {
            key: (bool(value.get("enabled")) if isinstance(value, dict) else True)
            for key, value in tool_cfg.items()
        }
        defaults.setdefault("parse", "xiongmao")
        defaults.setdefault("subtitles", "gemini")
        defaults.setdefault("dub", "lovo")
        defaults.setdefault("pack", "capcut")
        defaults.setdefault("face_swap", "none")

        pipeline_config = parse_pipeline_config(getattr(task, "pipeline_config", None))
        subtitles_mode = pipeline_config.get("subtitles_mode")
        dub_mode = pipeline_config.get("dub_mode")
        if dub_mode == "edge":
            defaults["dub"] = "edge-tts"
        elif dub_mode == "lovo":
            defaults["dub"] = "lovo"
        elif not getattr(settings, "lovo_api_key", None):
            defaults["dub"] = "edge-tts"

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

        def _disabled_step(step_name: str) -> bool:
            if enabled.get(step_name, True):
                return False
            task.status = "error"
            task.last_step = step_name
            task.error_message = f"Tool disabled: {step_name}"
            task.error_reason = f"Tool disabled: {step_name}"
            task.updated_at = datetime.utcnow()
            db.commit()
            return True

        # Parse
        if _disabled_step("parse"):
            return
        parse_provider = defaults.get("parse")
        parse_handler = get_provider("parse", parse_provider)
        parse_req = schemas.ParseRequest(
            task_id=task.id,
            platform=task.platform,
            link=task.source_url,
        )
        ok, parse_res = await _run_step("parse", parse_handler(parse_req))
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
        if _disabled_step("subtitles"):
            return
        subtitles_provider = defaults.get("subtitles")
        subtitles_handler = get_provider("subtitles", subtitles_provider)
        translate_enabled = subtitles_mode != "whisper-only"
        subs_req = schemas.SubtitlesRequest(
            task_id=task.id,
            target_lang=DEFAULT_MM_LANG,
            force=False,
            translate=translate_enabled,
            with_scenes=True,
        )
        ok, subs_res = await _run_step("subtitles", subtitles_handler(subs_req))
        if not ok:
            task.status = "error"
            task.last_step = "subtitles"
            task.error_message = str(subs_res)
            task.error_reason = str(subs_res)
            task.updated_at = datetime.utcnow()
            db.commit()
            return

        # Dub
        if _disabled_step("dub"):
            return
        dub_provider = defaults.get("dub")
        dub_handler = get_provider("dub", dub_provider)
        dub_req = schemas.DubRequest(
            task_id=task.id,
            voice_id=DEFAULT_MM_VOICE_ID,
            target_lang=DEFAULT_MM_LANG,
            force=False,
        )
        ok, dub_res = await _run_step("dub", dub_handler(dub_req))
        if not ok:
            task.status = "error"
            task.last_step = "dub"
            task.error_message = str(dub_res)
            task.error_reason = str(dub_res)
            task.updated_at = datetime.utcnow()
            db.commit()
            return

        if workspace.mm_audio_exists():
            task.mm_audio_path = relative_to_task_workspace(
                workspace.mm_audio_path, task.id
            )
        elif isinstance(dub_res, dict):
            audio_path_val = dub_res.get("audio_path") or dub_res.get("path")
            if audio_path_val:
                task.mm_audio_path = str(audio_path_val)
        db.commit()

        # Pack
        if _disabled_step("pack"):
            return
        pack_provider = defaults.get("pack")
        if pack_provider == "youcut":
            pack_provider = "capcut"
        pack_handler = get_provider("pack", pack_provider)
        pack_req = schemas.PackRequest(task_id=task.id)
        ok, pack_res = await _run_step("pack", pack_handler(pack_req))
        if not ok:
            task.status = "error"
            task.last_step = "pack"
            task.error_message = str(pack_res)
            task.error_reason = str(pack_res)
            task.updated_at = datetime.utcnow()
            db.commit()
            return

        pack_key = None
        if isinstance(pack_res, dict):
            pack_key = (
                pack_res.get("pack_key")
                or pack_res.get("zip_key")
                or pack_res.get("pack_path")
            )
        if pack_key:
            task.pack_key = str(pack_key)
            task.pack_type = "capcut_v18"
            task.pack_status = "ready"

        task.status = "ready"
        task.last_step = "pack"
        task.error_message = None
        task.error_reason = None
        task.updated_at = datetime.utcnow()
        db.commit()
        logger.info("Pipeline finished for task %s", task_id)
    except Exception as exc:  # pragma: no cover - defensive
        task.status = "error"
        task.last_step = task.last_step or "pipeline"
        task.error_message = str(exc)
        task.error_reason = str(exc)
        task.updated_at = datetime.utcnow()
        db.commit()
        logger.exception("Pipeline crashed for task %s", task_id)
