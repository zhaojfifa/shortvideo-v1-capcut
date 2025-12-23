import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from gateway.app.core.workspace import (
    Workspace,
    origin_srt_path,
    pack_zip_path,
    raw_path,
    translated_srt_path,
    workspace_root,
)
from gateway.app.db import Base, SessionLocal, engine, ensure_provider_config_table, ensure_task_extra_columns
from gateway.app import models
from gateway.app.services.artifact_storage import (
    get_download_url,
    object_exists,
    upload_task_artifact,
)
from gateway.app.routers import admin_publish, publish as publish_router, tasks as tasks_router
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
ALLOWED_TOP_DIRS = {"raw", "tasks", "audio", "pack", "published"}

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
app.include_router(publish_router.router)
app.include_router(admin_publish.router, tags=["admin"])
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
    key = _ensure_task_artifact_key(
        task_id=task_id,
        field="raw_path",
        local_path=raw_path(task_id),
        filename="raw.mp4",
        not_found="raw video not found",
    )
    return RedirectResponse(url=get_download_url(key), status_code=302)


@app.post("/v1/subtitles")
async def subtitles(request: SubtitlesRequest):
    return await run_subtitles_step(request)


@app.get("/v1/tasks/{task_id}/subs_origin")
async def get_origin_subs(task_id: str):
    key = _ensure_task_artifact_key(
        task_id=task_id,
        field="origin_srt_path",
        local_path=origin_srt_path(task_id),
        filename="origin.srt",
        not_found="origin subtitles not found",
    )
    return RedirectResponse(url=get_download_url(key), status_code=302)


@app.get("/v1/tasks/{task_id}/subs_mm")
async def get_mm_subs(task_id: str):
    mm_path = translated_srt_path(task_id, "my")
    if not mm_path.exists():
        mm_path = translated_srt_path(task_id, "mm")
    key = _ensure_task_artifact_key(
        task_id=task_id,
        field="mm_srt_path",
        local_path=mm_path,
        filename="mm.srt",
        not_found="burmese subtitles not found",
    )
    return RedirectResponse(url=get_download_url(key), status_code=302)


@app.post("/v1/dub")
async def dub(request: DubRequest):
    return await run_dub_step(request)


@app.get("/v1/tasks/{task_id}/audio_mm")
async def get_audio(task_id: str):
    workspace = Workspace(task_id)
    audio_path = workspace.mm_audio_path
    filename = f"mm_audio{audio_path.suffix or '.wav'}"
    key = _ensure_task_artifact_key(
        task_id=task_id,
        field="mm_audio_path",
        local_path=audio_path,
        filename=filename,
        not_found="dubbed audio not found",
    )
    return RedirectResponse(url=get_download_url(key), status_code=302)


@app.get("/v1/tasks/{task_id}/mm_txt")
async def get_mm_txt(task_id: str):
    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if task and task.mm_srt_path:
            key = str(task.mm_srt_path)
            txt_key = key[:-4] + ".txt" if key.endswith(".srt") else f"{key}.txt"
            if object_exists(txt_key):
                return RedirectResponse(url=get_download_url(txt_key), status_code=302)
    finally:
        db.close()

    workspace = Workspace(task_id)
    mm_srt = workspace.mm_srt_path
    mm_txt = mm_srt.with_suffix(".txt")
    if not mm_txt.exists():
        raise HTTPException(status_code=404, detail="mm txt not found")
    key = _ensure_task_loose_artifact_key(
        task_id=task_id,
        local_path=mm_txt,
        filename="mm.txt",
    )
    return RedirectResponse(url=get_download_url(key), status_code=302)


@app.post("/v1/pack")
async def pack(request: PackRequest):
    result = await run_pack_step(request)
    return result


def _ensure_task_artifact_key(
    task_id: str,
    field: str,
    local_path: Path,
    filename: str,
    not_found: str,
) -> str:
    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail=not_found)
        existing = getattr(task, field, None)
        if existing and object_exists(str(existing)):
            return str(existing)
        if not local_path.exists():
            raise HTTPException(status_code=404, detail=not_found)
        key = upload_task_artifact(task, local_path, filename, task_id=task_id)
        setattr(task, field, key)
        db.commit()
        return key
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        db.close()


def _ensure_task_loose_artifact_key(
    task_id: str,
    local_path: Path,
    filename: str,
) -> str:
    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="task not found")
        if not local_path.exists():
            raise HTTPException(status_code=404, detail="artifact not found")
        key = upload_task_artifact(task, local_path, filename, task_id=task_id)
        db.commit()
        return key
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        db.close()
