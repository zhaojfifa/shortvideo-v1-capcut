from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Optional

from gateway.adapters.s3_client import get_bucket_name, get_s3_client
from gateway.app.services.artifact_downloads import build_download_url, storage_available


def _task_value(task: Any, key: str) -> Optional[str]:
    if task is None:
        return None
    if isinstance(task, dict):
        value = task.get(key)
    else:
        value = getattr(task, key, None)
    return str(value) if value is not None else None


def task_storage_prefix(task: Any, task_id: Optional[str] = None) -> str:
    resolved_id = task_id or _task_value(task, "task_id") or _task_value(task, "id") or "unknown"
    return f"tasks/{resolved_id}"


def artifact_key(task: Any, filename: str, task_id: Optional[str] = None) -> str:
    prefix = task_storage_prefix(task, task_id=task_id)
    return f"{prefix}/{filename.lstrip('/')}"


def upload_task_artifact(
    task: Any,
    local_path: Path,
    filename: str,
    content_type: Optional[str] = None,
    task_id: Optional[str] = None,
) -> str:
    if not storage_available():
        raise RuntimeError("Storage is not configured")
    key = artifact_key(task, filename, task_id=task_id)
    client = get_s3_client()
    bucket = get_bucket_name()
    extra_args = {}
    inferred_type, _ = mimetypes.guess_type(str(local_path))
    resolved_type = content_type or inferred_type
    if resolved_type:
        extra_args["ContentType"] = resolved_type
    if extra_args:
        client.upload_file(str(local_path), bucket, key, ExtraArgs=extra_args)
    else:
        client.upload_file(str(local_path), bucket, key)
    return key


def get_download_url(key: str, expires_sec: int = 3600) -> str:
    return build_download_url(key, expires_sec=expires_sec)


def object_exists(key: str) -> bool:
    if not storage_available():
        return False
    client = get_s3_client()
    bucket = get_bucket_name()
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False
