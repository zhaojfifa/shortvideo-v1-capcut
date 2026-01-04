"""V1 routes exposing parse/subtitles/dub/pack and related assets."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from gateway.app.config import get_settings
from gateway.app.services.artifact_storage import get_download_url, object_exists
import logging
from gateway.app.db import SessionLocal
from gateway.app import models
from gateway.app.web.templates import get_templates
from gateway.app.core.workspace import (
    origin_srt_path,
    raw_path,
    translated_srt_path,
)
from gateway.app.schemas import DubRequest, PackRequest, ParseRequest, SubtitlesRequest
from gateway.app.services.steps_v1 import (
    run_dub_step,
    run_pack_step,
    run_parse_step,
    run_subtitles_step,
)

router = APIRouter()
templates = get_templates()
logger = logging.getLogger(__name__)


@router.get("/ui", response_class=HTMLResponse)
async def pipeline_lab(request: Request):
    settings = get_settings()
    env_summary = {
        "workspace_root": settings.workspace_root,
        "douyin_api_base": getattr(settings, "douyin_api_base", ""),
        "whisper_model": getattr(settings, "whisper_model", ""),
        "gpt_model": getattr(settings, "gpt_model", ""),
        "asr_backend": getattr(settings, "asr_backend", None) or "whisper",
        "subtitles_backend": getattr(settings, "subtitles_backend", None)
        or "gemini",
        "gemini_model": getattr(settings, "gemini_model", ""),
    }
    return templates.TemplateResponse(
        "pipeline_lab.html", {"request": request, "env_summary": env_summary}
    )


@router.post("/parse")
async def parse(request: ParseRequest):
    return await run_parse_step(request)


@router.get("/tasks/{task_id}/raw")
async def get_raw(task_id: str):
    path = raw_path(task_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="raw video not found")
    return FileResponse(path, media_type="video/mp4", filename=f"{task_id}.mp4")


@router.post("/subtitles")
async def subtitles(request: SubtitlesRequest):
    return await run_subtitles_step(request)


@router.get("/tasks/{task_id}/subs_origin")
async def get_origin_subs(task_id: str):
    origin = origin_srt_path(task_id)
    if not origin.exists():
        raise HTTPException(status_code=404, detail="origin subtitles not found")
    return FileResponse(origin, media_type="text/plain", filename=f"{task_id}_origin.srt")


@router.get("/tasks/{task_id}/subs_mm")
async def get_mm_subs(task_id: str):
    subs = translated_srt_path(task_id, "my")
    if not subs.exists():
        subs = translated_srt_path(task_id, "mm")
    if not subs.exists():
        raise HTTPException(status_code=404, detail="burmese subtitles not found")
    return FileResponse(subs, media_type="text/plain", filename=subs.name)


@router.post("/dub")
async def dub(request: DubRequest):
    return await run_dub_step(request)


@router.get("/tasks/{task_id}/audio_mm")
async def get_audio(task_id: str):
    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        key = str(task.mm_audio_key) if task and task.mm_audio_key else ""
        if key and object_exists(key):
            logger.info("audio_mm download: task_id=%s key=%s", task_id, key)
            presigned_url = get_download_url(
                key,
                expiration=3600,
                content_type="audio/mpeg",
                filename=f"{task_id}_audio_mm.mp3",
                disposition="attachment",
            )
            return RedirectResponse(url=presigned_url, status_code=302)
    finally:
        db.close()

    raise HTTPException(status_code=404, detail="dubbed audio not found")


@router.post("/pack")
async def pack(request: PackRequest):
    return await run_pack_step(request)


@router.get("/tasks/{task_id}/pack")
async def download_pack(task_id: str):
    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if task:
            key = str(task.pack_key or task.pack_path or "")
            if key and object_exists(key):
                presigned_url = get_download_url(
                    key,
                    expiration=3600,
                    content_type="application/zip",
                    filename=f"{task_id}_capcut_pack.zip",
                    disposition="attachment",
                )
                return RedirectResponse(url=presigned_url, status_code=302)
    finally:
        db.close()

    raise HTTPException(status_code=404, detail="pack not found")


@router.get("/tasks/{task_id}/scenes")
async def download_scenes(task_id: str):
    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if task and task.scenes_key:
            key = str(task.scenes_key)
            if object_exists(key):
                presigned_url = get_download_url(
                    key,
                    expiration=3600,
                    content_type="application/zip",
                    filename=f"{task_id}_scenes.zip",
                    disposition="attachment",
                )
                return RedirectResponse(url=presigned_url, status_code=302)
    finally:
        db.close()

    raise HTTPException(status_code=404, detail="Scenes not ready")
