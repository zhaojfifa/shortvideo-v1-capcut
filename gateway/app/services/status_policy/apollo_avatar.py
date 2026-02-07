from __future__ import annotations

from typing import Dict, Any

from .base import StatusPolicy


class ApolloAvatarStatusPolicy(StatusPolicy):
    """
    Rule: if publish bundle exists (publish_key present), the task must be READY and should not regress.
    This is intentionally conservative: it uses setdefault so explicit failure writes are not overridden.
    """

    def reconcile_after_step(
        self,
        task: Dict[str, Any],
        *,
        step: str,
        updates: Dict[str, Any],
        force: bool = False,
    ) -> Dict[str, Any]:
        merged = dict(task or {})
        merged.update(updates or {})

        publish_key = merged.get("publish_key")
        if publish_key:
            u = dict(updates or {})
            # do NOT override explicit failures; only prevent accidental regression
            u.setdefault("status", "ready")
            # apollo avatar UI expects "ready" gating; keep it stable
            u.setdefault("publish_status", "ready")
            # if pack exists, keep pack_status stable as well
            pack_key = merged.get("pack_key") or merged.get("pack_path")
            if pack_key:
                u.setdefault("pack_status", "ready")
            return u

        return updates or {}

