# gateway/app/task_repo_utils.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


def normalize_task_payload(task: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize task payload coming from different repositories / legacy formats.
    Must NEVER raise for missing optional fields (startup safety).
    """
    if not isinstance(task, dict):
        return {"raw": task}

    # id/task_id兼容
    task_id = task.get("task_id") or task.get("id")
    if task_id is not None:
        task["task_id"] = str(task_id)

    # created/created_at兼容（字符串保留原样，排序时处理）
    created = task.get("created_at") or task.get("created")
    if created is not None:
        task["created_at"] = created

    # title兜底
    if "title" not in task and "name" in task:
        task["title"] = task.get("name")

    return task


def _parse_dt(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, (int, float)):
        # unix seconds
        try:
            return datetime.fromtimestamp(v)
        except Exception:
            return None
    if isinstance(v, str):
        # try isoformat / common patterns
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def sort_tasks_by_created(items: List[Dict[str, Any]], descending: bool = True) -> List[Dict[str, Any]]:
    """
    Sort tasks by created_at/created. Must be stable and tolerant of bad values.
    """
    def key_fn(t: Dict[str, Any]) -> float:
        dt = _parse_dt(t.get("created_at") or t.get("created"))
        if dt is None:
            return 0.0
        try:
            return dt.timestamp()
        except Exception:
            return 0.0

    return sorted(items, key=key_fn, reverse=descending)
