"""Helpers for normalizing task payloads and ordering task lists."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _parse_created_at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def normalize_task_payload(payload: Dict[str, Any], *, is_new: bool = False) -> Dict[str, Any]:
    """Normalize task payload fields without raising on missing values."""

    payload = dict(payload or {})

    task_id = _coalesce(payload.get("task_id"), payload.get("id"))
    if task_id is not None:
        task_id_str = str(task_id)
        payload["task_id"] = task_id_str
        payload["id"] = task_id_str

    payload["tenant"] = "default"

    category_key = _coalesce(payload.get("category_key"), payload.get("category"))
    if category_key is not None:
        category_str = str(category_key)
        payload["category_key"] = category_str
        payload["category"] = category_str

    created_at = _coalesce(payload.get("created_at"), payload.get("created"))
    parsed_created = _parse_created_at(created_at)
    if parsed_created is not None:
        payload["created_at"] = parsed_created.isoformat()
    elif created_at is not None:
        payload["created_at"] = str(created_at)

    if is_new and payload.get("created_at") is None:
        payload["created_at"] = int(time.time())

    return payload


def sort_tasks_by_created(tasks: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return tasks sorted by created_at descending, defensive against bad data."""

    def sort_key(item: Dict[str, Any]) -> datetime:
        created_at = _coalesce(item.get("created_at"), item.get("created"))
        parsed = _parse_created_at(created_at)
        return parsed or datetime.min.replace(tzinfo=timezone.utc)

    return sorted(list(tasks or []), key=sort_key, reverse=True)
