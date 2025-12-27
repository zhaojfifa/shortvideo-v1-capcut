import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from gateway.app.core.workspace import workspace_root
from gateway.app.db import Base, SessionLocal, engine, ensure_provider_config_table, ensure_task_extra_columns
from gateway.app import models
from gateway.app.routers import admin_publish, publish as publish_router, tasks as tasks_router
from gateway.routes import admin_tools
from gateway.routes import v1 as v1_router

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
app.include_router(v1_router.router, prefix="/v1")


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


