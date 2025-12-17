import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from gateway.app.config import get_settings
from gateway.app.core.workspace import (
    Workspace,
    origin_srt_path,
    pack_zip_path,
    raw_path,
    translated_srt_path,
)
from gateway.app.db import Base, engine, ensure_task_extra_columns
from gateway.app.routers import tasks as tasks_router
from gateway.app.schemas import DubRequest, PackRequest, ParseRequest, SubtitlesRequest
from gateway.app.services.steps_v1 import (
    run_dub_step,
    run_pack_step,
    run_parse_step,
    run_subtitles_step,
)

app = FastAPI(title="ShortVideo Gateway", version="v1")
templates = Jinja2Templates(directory="gateway/app/templates")
logger = logging.getLogger(__name__)
tasks_html_path = Path(__file__).resolve().parent / "static" / "tasks.html"


@app.on_event("startup")
def on_startup() -> None:
    """Ensure database schema exists before serving traffic."""

    Base.metadata.create_all(bind=engine)
    ensure_task_extra_columns(engine)


app.include_router(tasks_router.router)


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


@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page() -> FileResponse:
    """Serve a minimal operator task list page backed by /api/tasks."""

    return FileResponse(tasks_html_path, media_type="text/html")


@app.post("/v1/parse")
async def parse(request: ParseRequest):
    return await run_parse_step(request)


@app.get("/v1/tasks/{task_id}/raw")
async def get_raw(task_id: str):
    path = raw_path(task_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="raw video not found")
    return FileResponse(path, media_type="video/mp4", filename=f"{task_id}.mp4")


@app.post("/v1/subtitles")
async def subtitles(request: SubtitlesRequest):
    return await run_subtitles_step(request)


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
    return await run_dub_step(request)


@app.get("/v1/tasks/{task_id}/audio_mm")
async def get_audio(task_id: str):
    workspace = Workspace(task_id)
    audio = workspace.mm_audio_path
    if not audio.exists():
        raise HTTPException(status_code=404, detail="dubbed audio not found")
    return FileResponse(audio, media_type=workspace.mm_audio_media_type(), filename=audio.name)


@app.post("/v1/pack")
async def pack(request: PackRequest):
    return await run_pack_step(request)


@app.get("/v1/tasks/{task_id}/pack")
async def download_pack(task_id: str):
    pack_file = pack_zip_path(task_id)
    if not pack_file.exists():
        raise HTTPException(status_code=404, detail="pack not found")
    return FileResponse(pack_file, media_type="application/zip", filename=pack_file.name)
