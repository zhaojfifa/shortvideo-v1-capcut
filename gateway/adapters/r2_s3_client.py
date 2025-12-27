"""Shared S3/R2 client helper using Render-provided env vars."""

from __future__ import annotations

import os

R2_ENDPOINT = os.getenv("R2_ENDPOINT") or os.getenv("R2_ENDPOINT_URL", "")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME") or os.getenv("R2_BUCKET", "")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY") or os.getenv("R2_ACCESS_KEY_ID", "")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY") or os.getenv("R2_SECRET_ACCESS_KEY", "")


def get_bucket_name() -> str:
    if not R2_BUCKET_NAME:
        raise RuntimeError("R2 bucket name is not configured")
    return R2_BUCKET_NAME


def get_s3_client():
    if not (R2_ENDPOINT and R2_ACCESS_KEY and R2_SECRET_KEY):
        raise RuntimeError("R2 S3 client is not configured")
    import boto3  # noqa: PLC0415
    from botocore.config import Config  # noqa: PLC0415

    endpoint_url = (R2_ENDPOINT or "").rstrip("/")
    config = Config(signature_version="s3v4", s3={"addressing_style": "path"})
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto",
        config=config,
    )
