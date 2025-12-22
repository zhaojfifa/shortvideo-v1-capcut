"""Port interface for task persistence (repository boundary)."""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class ITaskRepository(Protocol):
    """Task repository abstraction for create/get/list/update operations."""

    def create(self, task: Any) -> Any:
        """Persist a new task record and return the stored entity."""

    def get(self, task_id: str) -> Optional[Any]:
        """Return a task by id or None when missing."""

    def list(self, filters: Optional[dict[str, Any]] = None) -> list[Any]:
        """Return a list of tasks matching optional filters."""

    def upsert(self, task_id: str, payload: dict[str, Any]) -> Optional[Any]:
        """Insert or merge a task payload and return the stored task."""

    def update(self, task_id: str, patch: dict[str, Any]) -> Optional[Any]:
        """Backward-compatible alias for upsert."""
