# gateway/app/main.py

from pathlib import Path

import importlib.util
import logging
import os
import shutil
from typing import Any, Dict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from gateway.app.config import create_storage_service, get_settings
from gateway.app.db import Base, SessionLocal, engine, ensure_provider_config_table, ensure_task_extra_columns
from gateway.app import models
from gateway.app.ports.storage_provider import get_storage_service, set_storage_service
from gateway.app.routers import admin_publish, publish as publish_router, tasks as tasks_router
from gateway.app.routes.v17_pack import router as v17_pack_router
from gateway.routes import v1_actions

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
UI_HTML_PATH = STATIC_DIR / "ui.html"
AUDIO_DIR = Path(get_settings().workspace_root).expanduser().resolve() / "audio"
WORKSPACE_ROOT = Path(
    os.environ.get("VIDEO_WORKSPACE", "/opt/render/project/src/video_workspace")
).resolve()
ALLOWED_TOP_DIRS = {"raw", "tasks", "audio", "pack", "published"}

app = FastAPI(title="ShortVideo Gateway", version="v1")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR), check_dir=False), name="audio")
logger = logging.getLogger(__name__)
tasks_html_path = Path(__file__).resolve().parent / "static" / "tasks.html"


@app.on_event("startup")
def on_startup() -> None:
    # Initialize database schema on boot (safe no-op if tables already exist)
    Base.metadata.create_all(bind=engine)
    ensure_task_extra_columns(engine)
    ensure_provider_config_table(engine)
    set_storage_service(create_storage_service())
    for d in (Path("scenes"), Path("scene_packs"), Path("deliver/packs"), AUDIO_DIR):
        d.mkdir(parents=True, exist_ok=True)

@app.on_event("startup")
def log_routes_on_startup() -> None:
    """Log route table to help spot duplicates in CI/logs (dev-only signal)."""
    for route in app.routes:
        methods = ",".join(sorted(getattr(route, "methods", []) or []))
        path = getattr(route, "path", "")
        name = getattr(route, "name", "")
        logger.info("route=%s methods=%s name=%s", path, methods, name)

app.include_router(tasks_router.pages_router)
app.include_router(tasks_router.api_router)
app.include_router(v1_actions.router, prefix="/v1")
app.include_router(publish_router.router)
app.include_router(admin_publish.router, tags=["admin"])
app.include_router(v17_pack_router)


@app.get("/healthz/build", tags=["health"])
def healthz_build(response: Response) -> Dict[str, Any]:
    """
    Acceptance-only endpoint for v1.7.
    Must remain read-only, no side effects, no dependency on external services.
    """
    git_sha = (
        os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("GIT_SHA")
        or os.getenv("COMMIT_SHA")
        or "unknown"
    )

    # Check whether v1.7 Day1 module exists and is importable in the running container.
    has_pack_v17_youcut = False
    import_error = None
    try:
        from gateway.app.core.pack_v17_youcut import generate_youcut_pack  # noqa: F401

        has_pack_v17_youcut = True
    except Exception as e:
        import_error = f"{type(e).__name__}: {e}"

    payload: Dict[str, Any] = {
        "service": "shortvideo-v1-capcut",
        "version": "v1.7-day1",
        "git_sha": git_sha,
        "has_pack_v17_youcut": has_pack_v17_youcut,
        "edge_tts": importlib.util.find_spec("edge_tts") is not None,
        "r2_enabled": bool(
            os.getenv("R2_ENDPOINT")
            and os.getenv("R2_BUCKET_NAME")
            and os.getenv("R2_ACCESS_KEY")
            and os.getenv("R2_SECRET_KEY")
        ),
        "pack_v17_status": "frozen",
    }

    # Only attach error when import fails (helps debugging; still read-only)
    if import_error:
        payload["pack_v17_import_error"] = import_error

    # If v1.7 module is missing, mark as degraded to make it obvious in monitoring.
    if not has_pack_v17_youcut:
        response.status_code = 503

    return payload


@app.get("/healthz", tags=["health"])
def healthz() -> Dict[str, Any]:
    ffmpeg_available = bool(shutil.which("ffmpeg"))
    storage_ok = True
    storage_type = "unknown"
    try:
        storage = get_storage_service()
        storage_type = storage.__class__.__name__
    except Exception:
        storage_ok = False

    return {
        "status": "ok",
        "version": os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_SHA") or "unknown",
        "storage": storage_type,
        "storage_ok": storage_ok,
        "ffmpeg": ffmpeg_available,
    }


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


