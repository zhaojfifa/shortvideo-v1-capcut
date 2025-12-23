from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from gateway.adapters.s3_client import get_bucket_name, get_s3_client
from gateway.app.core.workspace import workspace_root


def _repo_backend() -> str:
    return (os.getenv("TASK_REPO_BACKEND") or os.getenv("STORAGE_BACKEND") or "").lower()


def _task_id_from_payload(task: dict) -> str:
    task_id = task.get("task_id") or task.get("id")
    if not task_id:
        raise ValueError("task payload missing task_id")
    return str(task_id)


def _tenant_from_payload(task: dict) -> str:
    return str(task.get("tenant") or task.get("account_id") or "default")


def _category_from_payload(task: dict) -> str:
    return str(task.get("category_key") or task.get("category") or "unknown")


def _file_task_path(task: dict) -> Path:
    task_id = _task_id_from_payload(task)
    tenant = _tenant_from_payload(task)
    category = _category_from_payload(task)
    return workspace_root() / "tasks" / tenant / category / f"{task_id}.json"


def _delete_s3_keys(keys: Iterable[str]) -> None:
    client = get_s3_client()
    bucket = get_bucket_name()
    for key in keys:
        if not key:
            continue
        client.delete_object(Bucket=bucket, Key=key)


def delete_task_record(task: dict) -> None:
    backend = _repo_backend()
    if backend in {"s3", "r2"}:
        task_id = _task_id_from_payload(task)
        client = get_s3_client()
        bucket = get_bucket_name()
        key = f"tasks/default/{task_id}.json"
        try:
            client.delete_object(Bucket=bucket, Key=key)
            return
        except Exception:
            pass
        prefix = "tasks/default/"
        token = None
        while True:
            params = {"Bucket": bucket, "Prefix": prefix}
            if token:
                params["ContinuationToken"] = token
            resp = client.list_objects_v2(**params)
            keys = [
                item.get("Key")
                for item in resp.get("Contents", [])
                if item.get("Key", "").endswith(f"/{task_id}.json")
            ]
            if keys:
                _delete_s3_keys(keys)
                return
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
        return

    path = _file_task_path(task)
    if path.exists():
        path.unlink()


def purge_task_artifacts(task: dict) -> int:
    task_id = _task_id_from_payload(task)
    prefix = f"tasks/{task_id}/"
    if len(prefix) < 10 or prefix.count("/") < 2:
        raise ValueError("Refusing to purge: invalid prefix")
    client = get_s3_client()
    bucket = get_bucket_name()
    deleted = 0
    token = None
    while True:
        params = {"Bucket": bucket, "Prefix": prefix}
        if token:
            params["ContinuationToken"] = token
        resp = client.list_objects_v2(**params)
        keys = [item.get("Key") for item in resp.get("Contents", []) if item.get("Key")]
        if keys:
            client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
            )
            deleted += len(keys)
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    return deleted
