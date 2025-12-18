"""Reusable pipeline step functions shared by /v1 routes and background tasks."""

import logging

from fastapi import HTTPException

from gateway.app.core.workspace import (
    Workspace,
    raw_path,
    translated_srt_path,
)
from gateway.app.services.dubbing import DubbingError, synthesize_voice
from gateway.app.services.pack import PackError, create_capcut_pack
from gateway.app.services.parse import detect_platform, parse_douyin_video
from gateway.app.services.subtitles import generate_subtitles
from gateway.app.schemas import DubRequest, PackRequest, ParseRequest, SubtitlesRequest

logger = logging.getLogger(__name__)


async def run_parse_step(req: ParseRequest):
    """Run the parse step for the given request."""

    try:
        platform = detect_platform(req.link, req.platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if platform != "douyin":
        raise HTTPException(
            status_code=400, detail=f"Unsupported platform for V1 parse: {platform}"
        )

    try:
        return await parse_douyin_video(req.task_id, req.link)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Unexpected error in parse step for task %s", req.task_id)
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {exc}") from exc


async def run_subtitles_step(req: SubtitlesRequest):
    """Run the subtitles step for the given request."""

    try:
        return await generate_subtitles(
            task_id=req.task_id,
            target_lang=req.target_lang,
            force=req.force,
            translate_enabled=req.translate,
            use_ffmpeg_extract=True,
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive logging for runtime issues
        logger.exception("Unexpected error in subtitles step for task %s", req.task_id)
        raise HTTPException(status_code=500, detail="internal error") from exc


async def run_dub_step(req: DubRequest):
    """Run the dubbing step for the given request."""

    workspace = Workspace(req.task_id)
    origin_exists = workspace.origin_srt_path.exists()
    mm_exists = workspace.mm_srt_exists()

    logger.info(
        "Dub request",
        extra={
            "task_id": req.task_id,
            "origin_srt_exists": origin_exists,
            "mm_srt_exists": mm_exists,
            "mm_srt_path": str(workspace.mm_srt_path),
        },
    )

    if not mm_exists:
        raise HTTPException(
            status_code=400,
            detail="translated subtitles not found; run /v1/subtitles first",
        )

    mm_text = workspace.read_mm_srt_text() or ""
    if not mm_text.strip():
        raise HTTPException(
            status_code=400,
            detail="translated subtitles file is empty; please rerun /v1/subtitles",
        )

    try:
        result = await synthesize_voice(
            task_id=req.task_id,
            target_lang=req.target_lang,
            voice_id=req.voice_id,
            force=req.force,
            mm_srt_text=mm_text,
            workspace=workspace,
        )
    except DubbingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audio_url = f"/v1/tasks/{req.task_id}/audio_mm"
    return {
        "task_id": req.task_id,
        "voice_id": req.voice_id,
        "audio_mm_url": audio_url,
        "duration_sec": result.get("duration_sec"),
        "audio_path": result.get("audio_path") or result.get("path"),
    }


async def run_pack_step(req: PackRequest):
    """Run the packaging step for the given request."""

    raw_file = raw_path(req.task_id)
    workspace = Workspace(req.task_id)
    audio_file = workspace.mm_audio_path
    subs_file = translated_srt_path(req.task_id, "my")
    if not subs_file.exists():
        subs_file = translated_srt_path(req.task_id, "mm")

    try:
        packed = create_capcut_pack(req.task_id, raw_file, audio_file, subs_file)
    except PackError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "task_id": req.task_id,
        "zip_path": packed.get("zip_path"),
        "files": packed.get("files"),
    }
