from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict


@dataclass(frozen=True)
class WorkbenchSpec:
    kind: str
    template: str
    js: Optional[str] = None
    display_name: Optional[str] = None


WORKBENCH_REGISTRY: Dict[str, WorkbenchSpec] = {
    "default": WorkbenchSpec(
        kind="default",
        template="task_workbench.html",
        js=None,
        display_name="Task Workbench",
    ),
    "apollo_avatar": WorkbenchSpec(
        kind="apollo_avatar",
        template="task_workbench_apollo_avatar.html",
        js="/static/js/workbench_apollo_avatar.js",
        display_name="Apollo Avatar Workbench",
    ),
}


def resolve_workbench_kind(task: dict) -> str:
    kind = None
    if isinstance(task, dict):
        kind = task.get("kind")
    else:
        kind = getattr(task, "kind", None)
    return kind or "default"


def resolve_workbench_spec(task: dict) -> WorkbenchSpec:
    kind = resolve_workbench_kind(task)
    return WORKBENCH_REGISTRY.get(kind, WORKBENCH_REGISTRY["default"])
