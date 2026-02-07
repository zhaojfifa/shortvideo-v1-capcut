from __future__ import annotations

from typing import Dict, Any

from .base import StatusPolicy


_TERMINAL_BAD = {"failed", "error"}
_REGRESSION_BAD = {"failed", "error", "processing"}


class ApolloAvatarStatusPolicy(StatusPolicy):
    """
    Prevent READY/DONE task from regressing to FAILED/ERROR/PROCESSING due to unrelated upserts.
    Only applies when deliverable is already present (publish_key/url/status done).
    """

    def reconcile_after_step(
        self,
        task: Dict[str, Any],
        *,
        step: str,
        updates: Dict[str, Any],
        force: bool = False,
    ) -> Dict[str, Any]:
        if not updates:
            return {}

        if force:
            return updates

        merged = dict(task or {})
        merged.update(updates or {})

        publish_key = merged.get("publish_key")
        publish_url = merged.get("publish_url")
        publish_status = str(merged.get("publish_status") or "").lower()

        deliverable_exists = bool(publish_key or publish_url or publish_status == "done")
        if not deliverable_exists:
            return updates

        cur_status = str((task or {}).get("status") or "").lower()
        cur_pack = str((task or {}).get("pack_status") or "").lower()
        cur_pub = str((task or {}).get("publish_status") or "").lower()

        u = dict(updates)

        def _drop_if_regress(field: str, cur_val: str) -> None:
            new_val = str(u.get(field) or "").lower()
            if not new_val:
                return
            if cur_val not in _TERMINAL_BAD and new_val in _REGRESSION_BAD:
                u.pop(field, None)

        _drop_if_regress("status", cur_status)
        _drop_if_regress("pack_status", cur_pack)
        _drop_if_regress("publish_status", cur_pub)

        if "last_step" in u and cur_status not in _TERMINAL_BAD:
            pass

        return u
