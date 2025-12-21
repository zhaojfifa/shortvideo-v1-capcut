"""S3/R2-backed task repository (Phase0 skeleton)."""

from __future__ import annotations

import json
from typing import Any, Optional

from gateway.adapters.s3_client import get_bucket_name, get_s3_client
from gateway.ports.task_repository import ITaskRepository


def _task_id_from_payload(task: dict[str, Any]) -> str:
    task_id = task.get("id") or task.get("task_id")
    if not task_id:
        raise ValueError("task payload missing id/task_id")
    return str(task_id)


def _category_from_payload(task: dict[str, Any]) -> str:
    return str(task.get("category") or task.get("category_key") or "unknown")


def _tenant_from_payload(task: dict[str, Any]) -> str:
    return str(task.get("tenant") or task.get("account_id") or "default")


def _task_key(tenant: str, category: str, task_id: str) -> str:
    return f"tasks/{tenant}/{category}/{task_id}.json"


class S3TaskRepository(ITaskRepository):
    """Task repository persisted as JSON objects in S3/R2."""

    def __init__(self, tenant: str = "default") -> None:
        self._tenant = tenant
        self._client = get_s3_client()
        self._bucket = get_bucket_name()

    def create(self, task: Any) -> Any:
        payload = dict(task)
        task_id = _task_id_from_payload(payload)
        tenant = _tenant_from_payload(payload)
        category = _category_from_payload(payload)
        key = _task_key(tenant, category, task_id)
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        return payload

    def get(self, task_id: str) -> Optional[Any]:
        tenant = self._tenant
        key = self._find_task_key(tenant, task_id)
        if not key:
            return None
        obj = self._client.get_object(Bucket=self._bucket, Key=key)
        payload = obj["Body"].read().decode("utf-8")
        return json.loads(payload)

    def list(self, filters: Optional[dict[str, Any]] = None) -> list[Any]:
        filters = filters or {}
        tenant = str(filters.get("tenant") or self._tenant or "default")
        prefix = f"tasks/{tenant}/"
        results: list[Any] = []
        response = self._client.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
        for item in response.get("Contents", []):
            key = item.get("Key")
            if not key:
                continue
            obj = self._client.get_object(Bucket=self._bucket, Key=key)
            payload = obj["Body"].read().decode("utf-8")
            results.append(json.loads(payload))
        return results

    def update(self, task_id: str, patch: dict[str, Any]) -> Optional[Any]:
        current = self.get(task_id)
        if not current:
            return None
        updated = dict(current)
        updated.update(patch)
        tenant = _tenant_from_payload(updated)
        category = _category_from_payload(updated)
        key = _task_key(tenant, category, task_id)
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=json.dumps(updated, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        return updated

    def _find_task_key(self, tenant: str, task_id: str) -> Optional[str]:
        prefix = f"tasks/{tenant}/"
        response = self._client.list_objects_v2(Bucket=self._bucket, Prefix=prefix)
        for item in response.get("Contents", []):
            key = item.get("Key", "")
            if key.endswith(f"/{task_id}.json"):
                return key
        return None
