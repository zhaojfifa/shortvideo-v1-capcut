"""Shared S3/R2 client helper using Render-provided env vars."""

from __future__ import annotations

import os


R2_ENDPOINT = os.getenv("R2_ENDPOINT", "")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY", "")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY", "")


def get_bucket_name() -> str:
    if not R2_BUCKET_NAME:
        raise RuntimeError("R2_BUCKET_NAME is not configured")
    return R2_BUCKET_NAME


def get_s3_client():
    if not (R2_ENDPOINT and R2_ACCESS_KEY and R2_SECRET_KEY):
        raise RuntimeError("R2 S3 client is not configured")
    import boto3  # noqa: PLC0415

    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto",
    )
