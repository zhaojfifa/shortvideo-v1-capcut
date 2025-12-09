import logging
import subprocess

import openai
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, HttpUrl

from gateway.app.config import Settings, get_settings
from gateway.app.core.workspace import (
    dubbed_audio_path,
    origin_srt_path,
    pack_zip_path,
    raw_path,
    relative_to_workspace,
    subs_dir,
    translated_srt_path,
)
from gateway.app.providers.xiongmao import XiongmaoError, parse_with_xiongmao
from gateway.app.services.dubbing import DubbingError, synthesize_voice
from gateway.app.services.download import DownloadError, download_raw_video
from gateway.app.services.pack import PackError, create_capcut_pack
from gateway.app.services.subtitles import SubtitleError, preview_lines
from gateway.app.services.gemini_subtitles import transcribe_and_translate_with_gemini
from gateway.app.services.subtitles import generate_subtitles_with_whisper

app = FastAPI(title="ShortVideo Gateway", version="v1")
templates = Jinja2Templates(directory="gateway/app/templates")
USE_FFMPEG_EXTRACT = True  # toggle to False only if ffmpeg is unavailable


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


async def _subtitles_with_openai(request: SubtitlesRequest, settings: Settings) -> dict:
    result = await generate_subtitles_with_whisper(
        settings,
        raw_path(request.task_id),
        request.task_id,
        target_lang=request.target_lang,
        force=request.force,
        translate_enabled=request.translate,
        use_ffmpeg_extract=USE_FFMPEG_EXTRACT,
    )

    return {
        "task_id": request.task_id,
        "origin_srt": result.get("origin_srt"),
        "mm_srt": result.get("mm_srt"),
        "wav": result.get("wav"),
        "segments_json": result.get("segments_json"),
        "origin_preview": result.get("origin_preview") or [],
        "mm_preview": result.get("mm_preview") or [],
        "scenes_preview": result.get("scenes_preview") or [],
    }


async def _subtitles_with_gemini(request: SubtitlesRequest, settings: Settings) -> dict:
    task_id = request.task_id
    raw_mp4 = raw_path(task_id)
    if not raw_mp4.exists():
        raise HTTPException(status_code=400, detail=f"raw video not found for task {task_id}")

    subs_root = subs_dir()
    subs_root.mkdir(parents=True, exist_ok=True)

    wav_path = subs_root / f"{task_id}.wav"
    origin_srt_path = subs_root / f"{task_id}_origin.srt"
    mm_srt_path = subs_root / f"{task_id}_mm.srt"

    if request.force or not wav_path.exists():
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(raw_mp4),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(wav_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise HTTPException(status_code=500, detail=f"ffmpeg failed: {proc.stderr[:400]}")

    try:
        origin_srt, mm_srt = transcribe_and_translate_with_gemini(
            wav_path, target_lang=request.target_lang or "my"
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # pragma: no cover - external dependency safety
        logging.exception("Gemini subtitles failed")
        raise HTTPException(status_code=502, detail="Gemini subtitles failed") from exc

    origin_srt_path.write_text(origin_srt, encoding="utf-8")
    mm_srt_path.write_text(mm_srt, encoding="utf-8")

    origin_preview = preview_lines(origin_srt)
    mm_preview = preview_lines(mm_srt)

    return {
        "task_id": task_id,
        "origin_srt": relative_to_workspace(origin_srt_path),
        "mm_srt": relative_to_workspace(mm_srt_path),
        "wav": relative_to_workspace(wav_path),
        "segments_json": None,
        "origin_preview": origin_preview,
        "mm_preview": mm_preview,
        "scenes_preview": [],
    }


@app.get("/ui", response_class=HTMLResponse)
async def pipeline_lab(request: Request):
    settings = get_settings()
    env_summary = {
        "workspace_root": settings.workspace_root,
        "douyin_api_base": getattr(settings, "douyin_api_base", ""),
        "whisper_model": getattr(settings, "whisper_model", ""),
        "gpt_model": getattr(settings, "gpt_model", ""),
        "asr_backend": getattr(settings, "asr_backend", "whisper"),
        "subtitles_backend": getattr(settings, "subtitles_backend", "gemini"),
        "gemini_model": getattr(settings, "gemini_model", ""),
    }
    return templates.TemplateResponse(
        "pipeline_lab.html", {"request": request, "env_summary": env_summary}
    )


@app.post("/v1/parse")
async def parse(request: ParseRequest):
    try:
        parsed = await parse_with_xiongmao(str(request.link))
        raw_file = await download_raw_video(request.task_id, parsed.get("download_url") or "")
    except XiongmaoError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except DownloadError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "task_id": request.task_id,
        "platform": request.platform,
        "title": parsed.get("title"),
        "type": parsed.get("type") or "VIDEO",
        "download_url": parsed.get("download_url"),
        "cover": parsed.get("cover"),
        "origin_text": parsed.get("origin_text"),
        "raw": parsed.get("raw"),
        "raw_exists": raw_file.exists(),
        "raw_path": relative_to_workspace(raw_file),
    }


@app.get("/v1/tasks/{task_id}/raw")
async def get_raw(task_id: str):
    path = raw_path(task_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="raw video not found")
    return FileResponse(path, media_type="video/mp4", filename=f"{task_id}.mp4")


@app.post("/v1/subtitles")
async def subtitles(
    request: SubtitlesRequest, settings: Settings = Depends(get_settings)
):
    raw_file = raw_path(request.task_id)
    if not raw_file.exists():
        raise HTTPException(status_code=400, detail="raw video not found")

    backend = getattr(settings, "subtitles_backend", "gemini")
    backend = (backend or "gemini").lower()

    try:
        if backend == "gemini":
            result = await _subtitles_with_gemini(request, settings)
        elif backend == "openai":
            result = await _subtitles_with_openai(request, settings)
        else:
            raise HTTPException(
                status_code=500, detail=f"Unknown subtitles backend: {backend}"
            )
    except HTTPException:
        raise
    except SubtitleError as exc:
        logging.exception("subtitles failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except openai.BadRequestError as exc:
        logging.exception("OpenAI error in /v1/subtitles")
        raise HTTPException(
            status_code=402, detail="OpenAI Whisper quota or billing error"
        ) from exc
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
    try:
        result = synthesize_voice(
            task_id=request.task_id,
            target_lang=request.target_lang,
            voice_id=request.voice_id,
            force=request.force,
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
