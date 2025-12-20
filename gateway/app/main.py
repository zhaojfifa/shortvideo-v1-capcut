import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from gateway.app.core.workspace import (
    Workspace,
    origin_srt_path,
    pack_zip_path,
    raw_path,
    relative_to_workspace,
    translated_srt_path,
    workspace_root,
)
from gateway.app.db import Base, SessionLocal, engine, ensure_provider_config_table, ensure_task_extra_columns
from gateway.app import models
from gateway.app.routers import tasks as tasks_router
from gateway.routes import admin_tools
from gateway.app.schemas import DubRequest, PackRequest, ParseRequest, SubtitlesRequest
from gateway.app.services.steps_v1 import (
    run_dub_step,
    run_pack_step,
    run_parse_step,
    run_subtitles_step,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
UI_HTML_PATH = STATIC_DIR / "ui.html"
AUDIO_DIR = workspace_root() / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_ROOT = Path(
    os.environ.get("VIDEO_WORKSPACE", "/opt/render/project/src/video_workspace")
).resolve()
ALLOWED_TOP_DIRS = {"raw", "tasks", "audio", "pack"}

app = FastAPI(title="ShortVideo Gateway", version="v1")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")
logger = logging.getLogger(__name__)
tasks_html_path = Path(__file__).resolve().parent / "static" / "tasks.html"


@app.on_event("startup")
def on_startup() -> None:
    # Initialize database schema on boot (safe no-op if tables already exist)
    Base.metadata.create_all(bind=engine)
    ensure_task_extra_columns(engine)
    ensure_provider_config_table(engine)

@app.on_event("startup")
def on_startup() -> None:
    """Ensure database schema exists before serving traffic."""

app.include_router(tasks_router.pages_router)
app.include_router(tasks_router.api_router)
app.include_router(admin_tools.router, tags=["admin"])
app.include_router(admin_tools.pages_router)


@app.get("/ui", response_class=HTMLResponse)
async def pipeline_lab():
    """Serve the dark pipeline lab page."""

    return UI_HTML_PATH.read_text(encoding="utf-8")


@app.get("/files/{rel_path:path}")
def serve_workspace_file(rel_path: str):
    rel_path = rel_path.lstrip("/")
    top = rel_path.split("/", 1)[0] if rel_path else ""
    if top not in ALLOWED_TOP_DIRS:
        raise HTTPException(status_code=404, detail="Not Found")

    file_path = (WORKSPACE_ROOT / rel_path).resolve()
    if not str(file_path).startswith(str(WORKSPACE_ROOT) + str(Path("/"))):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Not Found")

    return FileResponse(path=str(file_path))


@app.post("/v1/parse")
async def parse(request: ParseRequest):
    try:
        return await run_parse_step(request)
    except HTTPException as exc:
        from gateway.app.db import SessionLocal
        from gateway.app import models

        db = SessionLocal()
        try:
            task = db.query(models.Task).filter(models.Task.id == request.task_id).first()
            if task:
                task.status = "error"
                task.last_step = "parse"
                task.error_reason = "parse_failed"
                task.error_message = str(exc.detail)
                db.commit()
        finally:
            db.close()
        raise


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
    result = await run_pack_step(request)
    pack_file = pack_zip_path(request.task_id)
    if pack_file.exists():
        db = SessionLocal()
        try:
            task = db.query(models.Task).filter(models.Task.id == request.task_id).first()
            if task:
                task.pack_path = relative_to_workspace(pack_file)
                task.status = "ready"
                task.last_step = "pack"
                db.commit()
        finally:
            db.close()
    return result


@app.get("/v1/tasks/{task_id}/pack")
async def download_pack(task_id: str):
    pack_file = pack_zip_path(task_id)
    if not pack_file.exists():
        raise HTTPException(status_code=404, detail="pack not found")
    return FileResponse(pack_file, media_type="application/zip", filename=pack_file.name)
