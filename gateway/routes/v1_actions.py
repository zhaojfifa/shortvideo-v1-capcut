"""Thin v1 action routes for Pipeline Lab (POST only)."""

import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from gateway.app.schemas import DubRequest, PackRequest, ParseRequest, SubtitlesRequest
from gateway.app.services.steps_v1 import (
    _update_task,
    run_dub_step,
    run_pack_step,
    run_parse_step,
    run_subtitles_step,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _steps_async_enabled() -> bool:
    return os.getenv("RUN_STEPS_ASYNC", "1").strip().lower() not in ("0", "false", "no")


async def _run_subtitles_background(req: SubtitlesRequest) -> None:
    try:
        await run_subtitles_step(req)
    except HTTPException as exc:
        _update_task(req.task_id, subtitles_status="error", subtitles_error=f"{exc.status_code}: {exc.detail}")
        logger.exception(
            "SUB2_FAIL",
            extra={"task_id": req.task_id, "step": "subtitles", "phase": "exception"},
        )
    except Exception as exc:
        _update_task(req.task_id, subtitles_status="error", subtitles_error=str(exc))
        logger.exception(
            "SUB2_FAIL",
            extra={"task_id": req.task_id, "step": "subtitles", "phase": "exception"},
        )


async def _run_dub_background(req: DubRequest) -> None:
    try:
        await run_dub_step(req)
    except HTTPException as exc:
        _update_task(req.task_id, dub_status="error", dub_error=f"{exc.status_code}: {exc.detail}")
        logger.exception(
            "DUB3_FAIL",
            extra={"task_id": req.task_id, "step": "dub", "phase": "exception"},
        )
    except Exception as exc:
        _update_task(req.task_id, dub_status="error", dub_error=str(exc))
        logger.exception(
            "DUB3_FAIL",
            extra={"task_id": req.task_id, "step": "dub", "phase": "exception"},
        )


@router.post("/parse")
async def parse(request: ParseRequest):
    return await run_parse_step(request)


@router.post("/subtitles")
async def subtitles(request: SubtitlesRequest):
    if _steps_async_enabled():
        _update_task(request.task_id, subtitles_status="running", subtitles_error=None)
        asyncio.create_task(_run_subtitles_background(request))
        return JSONResponse(status_code=202, content={"queued": True, "task_id": request.task_id})
    return await run_subtitles_step(request)


@router.post("/dub")
async def dub(request: DubRequest):
    if _steps_async_enabled():
        _update_task(request.task_id, dub_status="running", dub_error=None)
        asyncio.create_task(_run_dub_background(request))
        return JSONResponse(status_code=202, content={"queued": True, "task_id": request.task_id})
    return await run_dub_step(request)


@router.post("/pack")
async def pack(request: PackRequest):
    return await run_pack_step(request)
