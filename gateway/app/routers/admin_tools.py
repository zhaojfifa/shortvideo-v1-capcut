from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from gateway.app.auth import require_admin_session
from gateway.app.providers.registry import AVAILABLE_PROVIDERS
from gateway.app.tools_config import get_defaults_structured, save_defaults_structured

router = APIRouter(prefix="/api/admin", tags=["admin"])


class ToolsPayload(BaseModel):
    tools: dict[str, dict[str, Any]]


def _normalize_tools(payload: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for step, cfg in (payload or {}).items():
        if step not in AVAILABLE_PROVIDERS:
            continue
        if not isinstance(cfg, dict):
            continue
        provider = cfg.get("provider")
        enabled = cfg.get("enabled")
        if isinstance(provider, str) and provider in AVAILABLE_PROVIDERS[step]:
            normalized.setdefault(step, {})["provider"] = provider
        if isinstance(enabled, bool):
            normalized.setdefault(step, {})["enabled"] = enabled
    return normalized


@router.get("/tools")
def get_tools(_: Any = Depends(require_admin_session)):
    defaults = get_defaults_structured()
    return {"tools": defaults, "available": AVAILABLE_PROVIDERS}


@router.post("/tools")
def save_tools(body: ToolsPayload, _: Any = Depends(require_admin_session)):
    tools_payload = _normalize_tools(body.tools)
    if not tools_payload:
        raise HTTPException(status_code=400, detail="Invalid tools payload")
    saved = save_defaults_structured(tools_payload)
    return {"ok": True, "tools": saved}
