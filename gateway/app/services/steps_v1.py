"""Reusable pipeline step functions shared by /v1 routes and background tasks."""

import logging
from pathlib import Path

from fastapi import HTTPException

from gateway.app.core.workspace import (
    Workspace,
    origin_srt_path,
    pack_zip_path,
    raw_path,
    relative_to_workspace,
    translated_srt_path,
)
from gateway.app.db import SessionLocal
from gateway.app import models
from gateway.app.services.artifact_storage import upload_task_artifact
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
        result = await parse_douyin_video(req.task_id, req.link)
        raw_file = raw_path(req.task_id)
        raw_key = None
        if raw_file.exists():
            raw_key = _upload_artifact(req.task_id, raw_file, "raw.mp4")
        _update_task(
            req.task_id,
            raw_path=raw_key,
            last_step="parse",
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Unexpected error in parse step for task %s", req.task_id)
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {exc}") from exc


async def run_subtitles_step(req: SubtitlesRequest):
    """Run the subtitles step for the given request."""

    try:
        result = await generate_subtitles(
            task_id=req.task_id,
            target_lang=req.target_lang,
            force=req.force,
            translate_enabled=req.translate,
            use_ffmpeg_extract=True,
        )
        workspace = Workspace(req.task_id)
        origin_key = None
        mm_key = None
        if workspace.origin_srt_path.exists():
            origin_key = _upload_artifact(req.task_id, workspace.origin_srt_path, "origin.srt")
        if workspace.mm_srt_path.exists():
            mm_key = _upload_artifact(req.task_id, workspace.mm_srt_path, "mm.srt")
            mm_txt_path = workspace.mm_srt_path.with_suffix(".txt")
            if mm_txt_path.exists():
                _upload_artifact(req.task_id, mm_txt_path, "mm.txt")
        _update_task(
            req.task_id,
            origin_srt_path=origin_key,
            mm_srt_path=mm_key,
            last_step="subtitles",
        )
        return result
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

    audio_path = result.get("audio_path") if isinstance(result, dict) else None
    audio_key = None
    if audio_path:
        path = Path(audio_path)
        if not path.is_absolute():
            path = workspace.mm_audio_path
        if path.exists():
            filename = f"mm_audio{path.suffix or '.wav'}"
            audio_key = _upload_artifact(req.task_id, path, filename)
    _update_task(req.task_id, mm_audio_path=audio_key, last_step="dub")

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
    subs_mm_srt = translated_srt_path(req.task_id, "my")
    if not subs_mm_srt.exists():
        subs_mm_srt = translated_srt_path(req.task_id, "mm")
    subs_mm_txt = subs_mm_srt.with_suffix(".txt")

    try:
        packed = create_capcut_pack(
            req.task_id,
            raw_file,
            audio_file,
            subs_mm_srt,
            subs_mm_txt,
        )
    except PackError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pack_path = packed.get("zip_path") if isinstance(packed, dict) else None
    if not pack_path:
        pack_file = pack_zip_path(req.task_id)
        if pack_file.exists():
            pack_path = relative_to_workspace(pack_file)

    pack_key = None
    if pack_path:
        pack_file = pack_zip_path(req.task_id)
        if pack_file.exists():
            pack_key = _upload_artifact(req.task_id, pack_file, "capcut_pack.zip")
    _update_task(
        req.task_id,
        pack_path=pack_key,
        status="ready",
        last_step="pack",
        error_message=None,
        error_reason=None,
    )

    return {
        "task_id": req.task_id,
        "zip_path": packed.get("zip_path"),
        "files": packed.get("files"),
    }


def _update_task(task_id: str, **fields) -> None:
    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            return
        for key, value in fields.items():
            if value is not None and hasattr(task, key):
                setattr(task, key, value)
        db.commit()
    finally:
        db.close()


def _upload_artifact(task_id: str, local_path: Path, filename: str) -> str | None:
    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            return None
        return upload_task_artifact(task, local_path, filename, task_id=task_id)
    finally:
        db.close()
