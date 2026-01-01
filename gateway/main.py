from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from gateway.routes import admin_tools, files, tasks, v1
from gateway.app.config import create_storage_service, get_settings
from gateway.app.db import Base, engine, ensure_provider_config_table, ensure_task_extra_columns
from gateway.app.ports.storage_provider import set_storage_service
from gateway.app.web.templates import get_templates

settings = None
try:
    from gateway.config import settings as _settings  # type: ignore

    settings = _settings
except Exception:
    settings = get_settings()

app = FastAPI(
    title="ShortVideo Gateway",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

if settings and getattr(settings, "cors_allow_origins", None):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_task_extra_columns(engine)
    ensure_provider_config_table(engine)
    set_storage_service(create_storage_service())


app.include_router(v1.router, prefix="/v1", tags=["v1"])
app.include_router(tasks.router, prefix="/api", tags=["tasks"])
app.include_router(tasks.pages_router)
app.include_router(files.router, tags=["files"])
app.include_router(admin_tools.router, tags=["admin"])
app.include_router(admin_tools.pages_router)

templates = get_templates()


@app.get("/ui", response_class=HTMLResponse)
async def pipeline_lab(request: Request):
    app_settings = get_settings()
    env_summary = {
        "workspace_root": app_settings.workspace_root,
        "douyin_api_base": getattr(app_settings, "douyin_api_base", ""),
        "whisper_model": getattr(app_settings, "whisper_model", ""),
        "gpt_model": getattr(app_settings, "gpt_model", ""),
        "asr_backend": getattr(app_settings, "asr_backend", None) or "whisper",
        "subtitles_backend": getattr(app_settings, "subtitles_backend", None)
        or "gemini",
        "gemini_model": getattr(app_settings, "gemini_model", ""),
    }
    return templates.TemplateResponse(
        "pipeline_lab.html", {"request": request, "env_summary": env_summary}
    )


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
