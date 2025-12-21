"""V1 routes exposing parse/subtitles/dub/pack and related assets."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from gateway.app.config import get_settings
from gateway.app.deps import get_task_repository
from gateway.app.web.templates import get_templates
from gateway.app.core.workspace import (
    Workspace,
    origin_srt_path,
    pack_zip_path,
    raw_path,
    relative_to_workspace,
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
    workspace = Workspace(task_id)
    audio = workspace.mm_audio_path
    if not audio.exists():
        raise HTTPException(status_code=404, detail="dubbed audio not found")
    return FileResponse(audio, media_type=workspace.mm_audio_media_type(), filename=audio.name)


@router.post("/pack")
async def pack(request: PackRequest):
    result = await run_pack_step(request)
    repo = get_task_repository()
    task = repo.get(request.task_id)
    if not task:
        return result

    rel_pack = None
    if isinstance(result, dict):
        rel_pack = (
            result.get("pack_path")
            or result.get("zip_path")
            or result.get("pack")
            or result.get("path")
        )

    if not rel_pack and task.get("pack_path"):
        rel_pack = task.get("pack_path")

    pack_file = None
    if rel_pack:
        ws_root = Path(get_settings().workspace_root)
        candidate = ws_root / rel_pack
        if candidate.exists():
            pack_file = candidate

    if not pack_file:
        candidates = [
            pack_zip_path(request.task_id),
            Path(get_settings().workspace_root)
            / "files"
            / "pack"
            / f"{request.task_id}_capcut_pack.zip",
            Path(get_settings().workspace_root)
            / "pack"
            / f"{request.task_id}_capcut_pack.zip",
        ]
        for candidate in candidates:
            if candidate.exists():
                pack_file = candidate
                break

    patch = {
        "status": "ready",
        "last_step": "pack",
        "error_message": None,
        "error_reason": None,
    }
    if pack_file and pack_file.exists():
        patch["pack_path"] = relative_to_workspace(pack_file)
    repo.update(request.task_id, patch)
    return result


@router.get("/tasks/{task_id}/pack")
async def download_pack(task_id: str):
    repo = get_task_repository()
    task = repo.get(task_id)
    if task and task.get("pack_path"):
        ws_root = Path(get_settings().workspace_root)
        pack_file = ws_root / task.get("pack_path")
        if pack_file.exists():
            return FileResponse(
                pack_file, media_type="application/zip", filename=pack_file.name
            )

    pack_file = pack_zip_path(task_id)
    if not pack_file.exists():
        raise HTTPException(status_code=404, detail="pack not found")
    return FileResponse(pack_file, media_type="application/zip", filename=pack_file.name)
