"""File-backed task repository (Phase0 default)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from gateway.app.core.workspace import workspace_root
from gateway.ports.task_repository import ITaskRepository


def _task_id_from_payload(task: dict[str, Any]) -> str:
    task_id = task.get("task_id") or task.get("id")
    if not task_id:
        raise ValueError("task payload missing task_id")
    return str(task_id)


def _category_from_payload(task: dict[str, Any]) -> str:
    return str(task.get("category_key") or task.get("category") or "unknown")


def _tenant_from_payload(task: dict[str, Any]) -> str:
    return str(task.get("tenant") or task.get("account_id") or "default")


def _task_path(base: Path, tenant: str, category: str, task_id: str) -> Path:
    return base / "tasks" / tenant / category / f"{task_id}.json"


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    with open(tmp_path, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _matches_filters(task: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, value in filters.items():
        if value is None:
            continue
        if str(task.get(key)) != str(value):
            return False
    return True


class FileTaskRepository(ITaskRepository):
    """Task repository persisted as JSON files on disk."""

    def __init__(self, tenant: str = "default") -> None:
        self._tenant = tenant
        self._base = workspace_root()

    def create_task(self, task: Any) -> Any:
        payload = dict(task)
        task_id = _task_id_from_payload(payload)
        tenant = _tenant_from_payload(payload)
        category = _category_from_payload(payload)
        path = _task_path(self._base, tenant, category, task_id)
        _atomic_write(path, payload)
        return payload

    def get_task(self, task_id: str) -> Optional[Any]:
        tenant = self._tenant
        base = self._base / "tasks" / tenant
        if not base.exists():
            return None
        for path in base.rglob(f"{task_id}.json"):
            return _load_json(path)
        return None

    def list_tasks(self, filters: Optional[dict[str, Any]] = None) -> list[Any]:
        filters = filters or {}
        tenant = str(filters.get("tenant") or self._tenant or "default")
        base = self._base / "tasks" / tenant
        if not base.exists():
            return []
        results: list[Any] = []
        for path in base.rglob("*.json"):
            payload = _load_json(path)
            if _matches_filters(payload, filters):
                results.append(payload)
        return results

    def upsert_task(self, task_id: str, patch: dict[str, Any]) -> Optional[Any]:
        current = self.get_task(task_id)
        if not current:
            current = {"task_id": task_id}
        updated = dict(current)
        updated.update(patch)
        tenant = _tenant_from_payload(updated)
        category = _category_from_payload(updated)
        path = _task_path(self._base, tenant, category, task_id)
        _atomic_write(path, updated)
        return updated

    def create(self, task: Any) -> Any:
        return self.create_task(task)

    def get(self, task_id: str) -> Optional[Any]:
        return self.get_task(task_id)

    def list(self, filters: Optional[dict[str, Any]] = None) -> list[Any]:
        return self.list_tasks(filters=filters)

    def update(self, task_id: str, patch: dict[str, Any]) -> Optional[Any]:
        return self.upsert_task(task_id, patch)

    def upsert(self, task_id: str, payload: dict[str, Any]) -> Optional[Any]:
        return self.upsert_task(task_id, payload)
