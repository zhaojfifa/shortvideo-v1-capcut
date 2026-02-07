from __future__ import annotations

from typing import Dict, Any


class StatusPolicy:
    """
    Default no-op policy. Subclasses can adjust updates to prevent status regression.
    """

    def reconcile_after_step(
        self,
        task: Dict[str, Any],
        *,
        step: str,
        updates: Dict[str, Any],
        force: bool = False,
    ) -> Dict[str, Any]:
        return updates or {}

