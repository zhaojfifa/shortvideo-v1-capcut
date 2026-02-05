from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_task_event(
    task: Dict[str, Any],
    *,
    channel: str,
    code: str,
    message: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    if extra is None:
        extra = {}
    events = task.get("events")
    if not isinstance(events, list):
        events = []
        task["events"] = events
    events.append(
        {
            "ts": utc_now_iso(),
            "channel": channel,
            "code": code,
            "message": message,
            "extra": extra,
        }
    )
