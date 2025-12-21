"""Pipeline orchestration to run parse → subtitles → dub → pack for a task."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

from fastapi import HTTPException
from gateway.app.config import get_settings
from gateway.app.db import engine
from gateway.app.core.workspace import (
    Workspace,
    get_task_workspace,
    pack_zip_path,
    raw_path,
    relative_to_task_workspace,
    relative_to_workspace,
)
from gateway.app import schemas
from gateway.app.deps import get_task_repository
from gateway.app.services.steps_v1 import (
    run_dub_step,
    run_pack_step,
    run_parse_step,
    run_subtitles_step,
)
from gateway.app.providers.registry import get_provider, resolve_tool_providers
logger = logging.getLogger(__name__)

DEFAULT_MM_LANG = os.getenv("DEFAULT_MM_LANG", "my")
DEFAULT_MM_VOICE_ID = os.getenv("DEFAULT_MM_VOICE_ID", "mm_female_1")


def get_defaults() -> dict:
    settings = get_settings()
    tools = resolve_tool_providers(engine, settings).get("tools", {})
    return {tool: config.get("provider") for tool, config in tools.items()}


def run_pipeline_background(task_id: str):
    """Entry point for FastAPI BackgroundTasks; manages its own DB session."""

    repo = get_task_repository()
    try:
        asyncio.run(run_pipeline_for_task(task_id, repo))
    except Exception as exc:
        repo.update(
            task_id,
            {
                "status": "error",
                "last_step": "pipeline",
                "error_reason": "pipeline_crash",
                "error_message": str(exc),
                "updated_at": datetime.utcnow().isoformat(),
            },
        )
        logger.exception("Pipeline crashed for task %s", task_id)


async def run_pipeline_for_task(task_id: str, repo):
    """Execute the V1 pipeline synchronously in sequence for the given task."""

    task = repo.get(task_id)
    if not task:
        logger.error("Task %s not found, abort pipeline", task_id)
        return

    try:
        tool_cfg = resolve_tool_providers(engine, get_settings()).get("tools", {})
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

        get_task_workspace(task_id)
        workspace = Workspace(task_id)

        logger.info(
            "Starting pipeline for task %s",
            task_id,
        )
        logger.info(
            "Pipeline context task=%s category=%s content_lang=%s ui_lang=%s video_type=%s face_swap_enabled=%s",
            task_id,
            task.get("category_key"),
            task.get("content_lang"),
            task.get("ui_lang"),
            task.get("video_type"),
            task.get("face_swap_enabled"),
        )
        repo.update(
            task_id,
            {
                "status": "processing",
                "last_step": None,
                "error_message": None,
                "error_reason": None,
                "updated_at": datetime.utcnow().isoformat(),
            },
        )

        async def _run_step(name: str, coro):
            try:
                result = await coro
                repo.update(task_id, {"last_step": name})
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
            repo.update(
                task_id,
                {
                    "status": "error",
                    "last_step": step_name,
                    "error_message": f"Tool disabled: {step_name}",
                    "error_reason": f"Tool disabled: {step_name}",
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )
            return True

        # Parse
        if _disabled_step("parse"):
            return
        parse_provider = defaults.get("parse")
        parse_handler = get_provider("parse", parse_provider)
        parse_req = schemas.ParseRequest(
            task_id=task_id,
            platform=task.get("platform"),
            link=task.get("source_url"),
        )
        ok, parse_res = await _run_step("parse", parse_handler(parse_req))
        if not ok:
            repo.update(
                task_id,
                {
                    "status": "error",
                    "last_step": "parse",
                    "error_message": str(parse_res),
                    "error_reason": str(parse_res),
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )
            return

        raw_file = raw_path(task_id)
        if raw_file.exists():
            repo.update(
                task_id, {"raw_path": relative_to_task_workspace(raw_file, task_id)}
            )
        if isinstance(parse_res, dict):
            duration_sec = parse_res.get("duration_sec")
        else:
            duration_sec = getattr(parse_res, "duration_sec", None)
        if duration_sec:
            repo.update(task_id, {"duration_sec": int(duration_sec)})

        # Subtitles
        if _disabled_step("subtitles"):
            return
        subtitles_provider = defaults.get("subtitles")
        subtitles_handler = get_provider("subtitles", subtitles_provider)
        subs_req = schemas.SubtitlesRequest(
            task_id=task_id,
            target_lang=DEFAULT_MM_LANG,
            force=False,
            translate=True,
            with_scenes=True,
        )
        ok, subs_res = await _run_step("subtitles", subtitles_handler(subs_req))
        if not ok:
            repo.update(
                task_id,
                {
                    "status": "error",
                    "last_step": "subtitles",
                    "error_message": str(subs_res),
                    "error_reason": str(subs_res),
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )
            return

        # Dub
        if _disabled_step("dub"):
            return
        dub_provider = defaults.get("dub")
        dub_handler = get_provider("dub", dub_provider)
        dub_req = schemas.DubRequest(
            task_id=task_id,
            voice_id=DEFAULT_MM_VOICE_ID,
            target_lang=DEFAULT_MM_LANG,
            force=False,
        )
        ok, dub_res = await _run_step("dub", dub_handler(dub_req))
        if not ok:
            repo.update(
                task_id,
                {
                    "status": "error",
                    "last_step": "dub",
                    "error_message": str(dub_res),
                    "error_reason": str(dub_res),
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )
            return

        if workspace.mm_audio_exists():
            repo.update(
                task_id,
                {
                    "mm_audio_path": relative_to_task_workspace(
                        workspace.mm_audio_path, task_id
                    )
                },
            )
        elif isinstance(dub_res, dict):
            audio_path_val = dub_res.get("audio_path") or dub_res.get("path")
            if audio_path_val:
                repo.update(task_id, {"mm_audio_path": str(audio_path_val)})

        # Pack
        if _disabled_step("pack"):
            return
        pack_provider = defaults.get("pack")
        pack_handler = get_provider("pack", pack_provider)
        pack_req = schemas.PackRequest(task_id=task_id)
        ok, pack_res = await _run_step("pack", pack_handler(pack_req))
        if not ok:
            repo.update(
                task_id,
                {
                    "status": "error",
                    "last_step": "pack",
                    "error_message": str(pack_res),
                    "error_reason": str(pack_res),
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )
            return

        pack_file = pack_zip_path(task_id)
        if pack_file.exists():
            repo.update(task_id, {"pack_path": relative_to_workspace(pack_file)})
        elif isinstance(pack_res, dict):
            maybe_pack = pack_res.get("pack_path") or pack_res.get("zip_path")
            if maybe_pack:
                repo.update(task_id, {"pack_path": str(maybe_pack)})

        repo.update(
            task_id,
            {
                "status": "ready",
                "last_step": "pack",
                "error_message": None,
                "error_reason": None,
                "updated_at": datetime.utcnow().isoformat(),
            },
        )
        logger.info("Pipeline finished for task %s", task_id)
    except Exception as exc:  # pragma: no cover - defensive
        repo.update(
            task_id,
            {
                "status": "error",
                "last_step": task.get("last_step") or "pipeline",
                "error_message": str(exc),
                "error_reason": str(exc),
                "updated_at": datetime.utcnow().isoformat(),
            },
        )
        logger.exception("Pipeline crashed for task %s", task_id)
