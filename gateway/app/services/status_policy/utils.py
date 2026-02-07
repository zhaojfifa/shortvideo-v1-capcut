from __future__ import annotations

from typing import Any, Dict, Optional

from .registry import get_status_policy


def policy_upsert(
    repo: Any,
    task_id: str,
    task: Optional[Dict[str, Any]],
    updates: Dict[str, Any],
    *,
    step: str,
    force: bool = False,
) -> Dict[str, Any]:
    cur = (repo.get(task_id) or task or {})
    policy = get_status_policy(cur)

    filtered = policy.reconcile_after_step(
        cur,
        step=step,
        updates=dict(updates or {}),
        force=force,
    ) or {}

    if filtered:
        repo.upsert(task_id, filtered)
        return repo.get(task_id) or cur

    return cur
