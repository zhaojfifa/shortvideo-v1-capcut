from typing import Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from gateway.app.tools_config import get_defaults, save_defaults
from gateway.app.tools_registry import registry

router = APIRouter()
pages_router = APIRouter()
templates = Jinja2Templates(directory="gateway/app/templates")


class ToolsDefaultsPayload(BaseModel):
    defaults: Dict[str, str]


@router.get("/admin/tools")
def get_tools():
    return {"defaults": get_defaults(), "providers": registry.list()}


@router.post("/admin/tools")
def update_tools(payload: ToolsDefaultsPayload):
    providers = registry.list()
    for tool_type, name in payload.defaults.items():
        if tool_type not in providers:
            raise HTTPException(status_code=400, detail=f"Unknown tool type: {tool_type}")
        if name not in providers[tool_type]:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown provider for {tool_type}: {name}",
            )
    defaults = save_defaults(payload.defaults)
    return {"defaults": defaults, "providers": providers}


@pages_router.get("/admin/tools", response_class=HTMLResponse)
def admin_tools_page(request: Request):
    return templates.TemplateResponse("admin_tools.html", {"request": request})
