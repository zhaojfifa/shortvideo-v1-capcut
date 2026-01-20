from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from gateway.app.services.tools_registry import get_tool, list_tools, redact_tool, redact_tools

router = APIRouter(prefix="/api", tags=["tools"])


def _http500(message: str) -> HTTPException:
    return HTTPException(status_code=500, detail=message)


@router.get("/tools")
def list_tools_api(
    category: str | None = Query(default=None),
    capabilities: str | None = Query(default=None),
    tags: str | None = Query(default=None),
    integration_level: str | None = Query(default=None),
    status_state: str | None = Query(default=None),
    q: str | None = Query(default=None),
):
    try:
        tools = list_tools(
            category=category,
            capabilities=capabilities,
            tags=tags,
            integration_level=integration_level,
            status_state=status_state,
            q=q,
        )
    except RuntimeError as exc:
        raise _http500(str(exc)) from exc
    return {"items": redact_tools(tools), "total": len(tools)}


@router.get("/tools/{tool_id}")
def get_tool_api(tool_id: str):
    try:
        tool = get_tool(tool_id)
    except RuntimeError as exc:
        raise _http500(str(exc)) from exc
    if not tool:
        raise HTTPException(status_code=404, detail="tool not found")
    return redact_tool(tool)
