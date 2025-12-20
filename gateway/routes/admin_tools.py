from typing import Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from gateway.app.config import get_settings
from gateway.app.db import engine, set_provider_config_map
from gateway.app.providers.registry import AVAILABLE_PROVIDERS, resolve_tool_providers
from gateway.app.web.templates import get_templates

router = APIRouter()
pages_router = APIRouter()
templates = get_templates()


class ToolEntry(BaseModel):
    provider: str
    enabled: bool


class ToolsPayload(BaseModel):
    tools: Dict[str, ToolEntry]


@router.get("/api/admin/tools")
def get_tools():
    settings = get_settings()
    return resolve_tool_providers(engine, settings)


@router.post("/api/admin/tools")
def update_tools(payload: ToolsPayload):
    updates: Dict[str, str] = {}
    for tool, entry in payload.tools.items():
        available = AVAILABLE_PROVIDERS.get(tool)
        if not available:
            raise HTTPException(status_code=400, detail=f"Unknown tool type: {tool}")
        if entry.provider not in available:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown provider for {tool}: {entry.provider}",
            )
        updates[f"{tool}_provider"] = entry.provider
        updates[f"{tool}_enabled"] = "true" if entry.enabled else "false"

    set_provider_config_map(engine, updates)
    settings = get_settings()
    return resolve_tool_providers(engine, settings)


@pages_router.get("/admin/tools", response_class=HTMLResponse)
def admin_tools_page(request: Request):
    return templates.TemplateResponse("admin_tools.html", {"request": request})
