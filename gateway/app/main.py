import logging
import subprocess

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, HttpUrl

from gateway.app.config import get_settings
from gateway.app.core.workspace import (
    Workspace,
    dubbed_audio_path,
    origin_srt_path,
    pack_zip_path,
    raw_path,
    translated_srt_path,
)
from gateway.app.services.dubbing import DubbingError, synthesize_voice
from gateway.app.services.parse import parse_douyin_video
from gateway.app.services.pack import PackError, create_capcut_pack
from gateway.app.services.subtitles import generate_subtitles

app = FastAPI(title="ShortVideo Gateway", version="v1")
templates = Jinja2Templates(directory="gateway/app/templates")
USE_FFMPEG_EXTRACT = True  # toggle to False only if ffmpeg is unavailable
logger = logging.getLogger(__name__)


class ParseRequest(BaseModel):
    task_id: str
    platform: str | None = None
    link: HttpUrl


class SubtitlesRequest(BaseModel):
    task_id: str
    target_lang: str = "my"
    force: bool = False
    translate: bool = True
    with_scenes: bool = True


class DubRequest(BaseModel):
    task_id: str
    voice_id: str | None = None
    target_lang: str = "my"
    force: bool = False


class PackRequest(BaseModel):
    task_id: str


@app.get("/ui", response_class=HTMLResponse)
async def pipeline_lab(request: Request):
    settings = get_settings()
    env_summary = {
        "workspace_root": settings.workspace_root,
        "douyin_api_base": getattr(settings, "douyin_api_base", ""),
        "whisper_model": getattr(settings, "whisper_model", ""),
        "gpt_model": getattr(settings, "gpt_model", ""),
        "asr_backend": "whisper",
        "subtitles_backend": "gemini",
        "gemini_model": getattr(settings, "gemini_model", ""),
    }
    return templates.TemplateResponse(
        "pipeline_lab.html", {"request": request, "env_summary": env_summary}
    )


@app.post("/v1/parse")
async def parse(request: ParseRequest):
    platform = request.platform or "douyin"
    if platform != "douyin":
        raise HTTPException(status_code=400, detail="Only 'douyin' is supported in V1 parse")

    try:
        return await parse_douyin_video(request.task_id, str(request.link))
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Unexpected error in /v1/parse for task %s", request.task_id)
        raise HTTPException(status_code=500, detail=f"Unexpected server error: {exc}") from exc


@app.get("/v1/tasks/{task_id}/raw")
async def get_raw(task_id: str):
    path = raw_path(task_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="raw video not found")
    return FileResponse(path, media_type="video/mp4", filename=f"{task_id}.mp4")


@app.post("/v1/subtitles")
async def subtitles(request: SubtitlesRequest):
    try:
        result = await generate_subtitles(
            task_id=request.task_id,
            target_lang=request.target_lang,
            force=request.force,
            translate_enabled=request.translate,
            use_ffmpeg_extract=USE_FFMPEG_EXTRACT,
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive logging for runtime issues
        logging.exception("Unexpected error in /v1/subtitles")
        raise HTTPException(status_code=500, detail="internal error") from exc

    return result


@app.get("/v1/tasks/{task_id}/subs_origin")
async def get_origin_subs(task_id: str):
    origin = origin_srt_path(task_id)
    if not origin.exists():
        raise HTTPException(status_code=404, detail="origin subtitles not found")
    return FileResponse(origin, media_type="text/plain", filename=f"{task_id}_origin.srt")


@app.get("/v1/tasks/{task_id}/subs_mm")
async def get_mm_subs(task_id: str):
    subs = translated_srt_path(task_id, "my")
    if not subs.exists():
        subs = translated_srt_path(task_id, "mm")
    if not subs.exists():
        raise HTTPException(status_code=404, detail="burmese subtitles not found")
    return FileResponse(subs, media_type="text/plain", filename=subs.name)


@app.post("/v1/dub")
async def dub(request: DubRequest):
    workspace = Workspace(request.task_id)
    origin_exists = workspace.origin_srt_path.exists()
    mm_exists = workspace.mm_srt_exists()

    logger.info(
        "Dub request",
        extra={
            "task_id": request.task_id,
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
        result = synthesize_voice(
            task_id=request.task_id,
            target_lang=request.target_lang,
            voice_id=request.voice_id,
            force=request.force,
            mm_srt_text=mm_text,
            workspace=workspace,
        )
    except DubbingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "task_id": request.task_id,
        "voice_id": request.voice_id,
        "audio_path": result.get("audio_path"),
        "duration_sec": result.get("duration_sec"),
    }


@app.get("/v1/tasks/{task_id}/audio_mm")
async def get_audio(task_id: str):
    audio = dubbed_audio_path(task_id)
    if not audio.exists():
        raise HTTPException(status_code=404, detail="dubbed audio not found")
    return FileResponse(audio, media_type="audio/wav", filename=audio.name)


@app.post("/v1/pack")
async def pack(request: PackRequest):
    raw_file = raw_path(request.task_id)
    audio_file = dubbed_audio_path(request.task_id)
    subs_file = translated_srt_path(request.task_id, "my")
    if not subs_file.exists():
        subs_file = translated_srt_path(request.task_id, "mm")

    try:
        packed = create_capcut_pack(request.task_id, raw_file, audio_file, subs_file)
    except PackError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "task_id": request.task_id,
        "zip_path": packed.get("zip_path"),
        "files": packed.get("files"),
    }


@app.get("/v1/tasks/{task_id}/pack")
async def download_pack(task_id: str):
    pack_file = pack_zip_path(task_id)
    if not pack_file.exists():
        raise HTTPException(status_code=404, detail="pack not found")
    return FileResponse(pack_file, media_type="application/zip", filename=pack_file.name)
