# gateway/app/main.py

from pathlib import Path

import importlib.util
import logging
import os
import shutil
from typing import Any, Dict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from gateway.app.auth import (
    COOKIE_NAME,
    load_auth_settings,
    scopes_for_role,
    verify_op_key,
    verify_session,
)
from gateway.app.config import create_storage_service, get_settings
from gateway.app.core.logging_config import configure_logging
from gateway.app.db import Base, SessionLocal, engine, ensure_provider_config_table, ensure_task_extra_columns
from gateway.app import models
from gateway.app.ports.storage_provider import get_storage_service, set_storage_service
from gateway.app.routers import admin_publish, admin_tools as admin_tools_router, publish as publish_router, tasks as tasks_router
from gateway.app.routers import hot_follow_ui as hot_follow_ui_router
from gateway.app.routers.api_tools import router as tools_api_router
from gateway.app.routes.auth import router as auth_router
from gateway.app.routes.v17_pack import router as v17_pack_router
from gateway.app.web.templates import render_template
from gateway.routes import v1_actions

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
UI_HTML_PATH = STATIC_DIR / "ui.html"
AUDIO_DIR = Path(get_settings().workspace_root).expanduser().resolve() / "audio"
WORKSPACE_ROOT = Path(
    os.environ.get("VIDEO_WORKSPACE", "/opt/render/project/src/video_workspace")
).resolve()
ALLOWED_TOP_DIRS = {"raw", "tasks", "audio", "pack", "published"}

configure_logging()

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
def warmup_whisper_on_startup() -> None:
    try:
        from gateway.app.providers import whisper_singleton

        whisper_singleton.get_whisper_model()
        whisper_singleton.warmup()
    except Exception as exc:
        logger.warning("startup whisper warmup failed: %s", exc)

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
app.include_router(auth_router)
app.include_router(tools_api_router)
app.include_router(v1_actions.router, prefix="/v1")
app.include_router(publish_router.router)
app.include_router(admin_publish.router, tags=["admin"])
app.include_router(admin_tools_router.router)
app.include_router(v17_pack_router)
app.include_router(hot_follow_ui_router.router)
if get_settings().enable_apollo_avatar:
    from gateway.app.routers.apollo_avatar import router as apollo_avatar_router

    app.include_router(apollo_avatar_router)

ALLOW_PREFIXES = (
    "/health",
    "/healthz",
    "/static/",
    "/auth/login",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/me",
)
ADMIN_PREFIXES = ("/admin", "/api/admin")


def _is_allowed_path(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in ALLOW_PREFIXES)


def _is_api_path(path: str) -> bool:
    return path.startswith("/api/") or path.startswith("/v1/")


def _is_admin_area(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in ADMIN_PREFIXES)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if _is_allowed_path(path):
        return await call_next(request)

    s = load_auth_settings()
    if s.auth_mode == "off":
        return await call_next(request)

    header_ok = False
    if s.auth_mode in ("header", "both"):
        hv = request.headers.get(s.header_name)
        header_ok = verify_op_key(hv, s.op_access_key)
        if header_ok:
            request.state.op = "header"
            request.state.role = "operator"
            request.state.scopes = scopes_for_role("operator")

    session_ok = False
    if not header_ok and s.auth_mode in ("session", "both"):
        token = request.cookies.get(COOKIE_NAME)
        claims = verify_session(token, s.session_secret) if token else None
        if claims:
            role = claims.get("role", "operator")
            request.state.op = claims.get("op", "ops")
            request.state.role = role
            request.state.scopes = scopes_for_role(role)
            session_ok = True

    if header_ok or session_ok:
        if _is_admin_area(path):
            role = getattr(request.state, "role", "")
            if str(role).lower() != "admin":
                return JSONResponse(status_code=403, content={"detail": "Admin only"})
        return await call_next(request)

    if _is_api_path(path):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    next_url = str(request.url.path)
    if request.url.query:
        next_url += "?" + request.url.query
    return RedirectResponse(url=f"/auth/login?next={next_url}", status_code=302)


@app.get("/auth/login", response_class=HTMLResponse, include_in_schema=False)
def auth_login_page(request: Request, next: str = "/tasks"):
    return render_template(
        request=request,
        name="auth_login.html",
        ctx={
            "next": next,
            "topbar_title": None,
            "topbar_nav": None,
            "topbar_actions": None,
        },
    )


@app.get("/admin/tools", response_class=HTMLResponse, include_in_schema=False)
def admin_tools_page(request: Request):
    return render_template(request=request, name="admin_tools.html")


@app.get("/", include_in_schema=False)
def root() -> Dict[str, Any]:
    return {"ok": True}


@app.head("/", include_in_schema=False)
def root_head() -> Response:
    return Response(status_code=200)


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


