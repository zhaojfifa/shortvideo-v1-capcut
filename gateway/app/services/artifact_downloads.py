from __future__ import annotations

import os
from typing import Optional

from gateway.adapters.s3_client import get_bucket_name, get_s3_client

R2_PUBLIC_BASE_URL = os.getenv("R2_PUBLIC_BASE_URL", "")


def storage_available() -> bool:
    try:
        get_bucket_name()
        get_s3_client()
    except (RuntimeError, ModuleNotFoundError):
        return False
    return True


def _normalize_storage_key(value: str) -> str:
    candidate = value.strip()
    if candidate.startswith("http://") or candidate.startswith("https://"):
        return candidate
    if candidate.startswith(("s3://", "r2://")):
        without_scheme = candidate.split("://", 1)[1]
        if "/" in without_scheme:
            _, key = without_scheme.split("/", 1)
            return key
        return without_scheme
    return candidate.lstrip("/")


def build_download_url(key: str, expires_sec: int = 3600) -> str:
    normalized = _normalize_storage_key(key)
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized
    if R2_PUBLIC_BASE_URL:
        return f"{R2_PUBLIC_BASE_URL.rstrip('/')}/{normalized}"
    client = get_s3_client()
    bucket = get_bucket_name()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": normalized},
        ExpiresIn=expires_sec,
    )


def resolve_storage_url(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if not storage_available():
        return None
    return build_download_url(value)
