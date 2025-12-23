from __future__ import annotations

import os
from pathlib import Path


R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL", "")
R2_BUCKET = os.getenv("R2_BUCKET", "")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "")
R2_REGION = os.getenv("R2_REGION", "auto")
FEATURE_STORAGE_ENABLED = os.getenv("FEATURE_STORAGE_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
SIGNED_URL_EXPIRES = int(os.getenv("SIGNED_URL_EXPIRES", "900"))


def _ensure_enabled() -> None:
    if not FEATURE_STORAGE_ENABLED:
        raise RuntimeError("Storage is disabled (FEATURE_STORAGE_ENABLED=false)")
    if not (R2_ENDPOINT_URL and R2_BUCKET and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY):
        raise RuntimeError("R2 storage is not configured (missing R2_* envs)")


def _client():
    import boto3  # noqa: PLC0415

    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT_URL,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name=R2_REGION or "auto",
    )


def enabled() -> bool:
    try:
        _ensure_enabled()
    except RuntimeError:
        return False
    return True


def key_for(task_id: str, artifact: str) -> str:
    safe_task = str(task_id).strip()
    safe_artifact = artifact.lstrip("/")
    return f"tasks/{safe_task}/{safe_artifact}"


def ensure_uploaded(local_path: Path, key: str) -> None:
    _ensure_enabled()
    if not local_path.exists():
        raise FileNotFoundError(str(local_path))
    client = _client()
    client.upload_file(str(local_path), R2_BUCKET, key)


def presign_get(key: str, filename: str | None = None) -> str:
    _ensure_enabled()
    client = _client()
    params = {"Bucket": R2_BUCKET, "Key": key}
    if filename:
        params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
    return client.generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=SIGNED_URL_EXPIRES,
    )
