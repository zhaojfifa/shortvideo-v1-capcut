from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

REGISTRY_PATH = Path("data/tools_registry.json")


def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        raise RuntimeError(f"tools registry missing: {REGISTRY_PATH}")
    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"tools registry invalid: {exc}") from exc


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _matches_any(values: Iterable[str], needles: Iterable[str]) -> bool:
    values_set = {v for v in values if v}
    needles_set = {n for n in needles if n}
    if not needles_set:
        return True
    return bool(values_set.intersection(needles_set))


def redact_tool(tool: dict[str, Any]) -> dict[str, Any]:
    sanitized = json.loads(json.dumps(tool))
    auth = sanitized.get("auth")
    if isinstance(auth, dict):
        auth.pop("secret_ref", None)
    return sanitized


def redact_tools(tools: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [redact_tool(t) for t in tools]


def list_tools(
    *,
    category: str | None = None,
    capabilities: str | None = None,
    tags: str | None = None,
    integration_level: str | None = None,
    status_state: str | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    registry = load_registry()
    tools = registry.get("tools") or []

    cap_list = _split_csv(capabilities)
    tag_list = _split_csv(tags)
    q_text = (q or "").strip().lower()

    filtered: list[dict[str, Any]] = []
    for tool in tools:
        if category and tool.get("category") != category:
            continue
        if integration_level and (tool.get("integration") or {}).get("level") != integration_level:
            continue
        if status_state and (tool.get("status") or {}).get("state") != status_state:
            continue
        if not _matches_any(tool.get("capabilities") or [], cap_list):
            continue
        if not _matches_any(tool.get("tags") or [], tag_list):
            continue
        if q_text:
            name = tool.get("name") or {}
            fields = [
                tool.get("tool_id") or "",
                name.get("zh") or "",
                name.get("en") or "",
                name.get("mm") or "",
                (tool.get("ui") or {}).get("short_desc") or "",
            ]
            hay = " ".join(fields).lower()
            if q_text not in hay:
                continue
        filtered.append(tool)

    def sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
        ui = item.get("ui") or {}
        sort_weight = ui.get("sort_weight") or 0
        recommended = 1 if ui.get("recommended") else 0
        return (-int(sort_weight), -recommended, str(item.get("tool_id") or ""))

    filtered.sort(key=sort_key)
    return filtered


def get_tool(tool_id: str) -> dict[str, Any] | None:
    registry = load_registry()
    for tool in registry.get("tools") or []:
        if tool.get("tool_id") == tool_id:
            return tool
    return None
