import asyncio
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from gateway.app.core.workspace import raw_path


class DownloadError(Exception):
    """Raised when raw video download fails."""


logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


async def download_raw_video(task_id: str, url: str) -> Path:
    if not url:
        raise DownloadError("missing download url")

    destination = raw_path(task_id)
    url_host = urlparse(url).netloc
    retries = _env_int("DOWNLOAD_RETRIES", 2)
    connect_timeout = _env_int("DOWNLOAD_CONNECT_TIMEOUT_SEC", 10)
    read_timeout = _env_int("DOWNLOAD_READ_TIMEOUT_SEC", 60)
    write_timeout = _env_int("DOWNLOAD_WRITE_TIMEOUT_SEC", 60)
    pool_timeout = _env_int("DOWNLOAD_POOL_TIMEOUT_SEC", 10)
    timeout = httpx.Timeout(
        connect=connect_timeout,
        read=read_timeout,
        write=write_timeout,
        pool=pool_timeout,
    )
    last_exc: Exception | None = None

    for attempt in range(1, retries + 2):
        start_time = time.perf_counter()
        bytes_written = 0
        status_code = None
        content_length = None
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("GET", url) as response:
                    status_code = response.status_code
                    content_length = response.headers.get("content-length")
                    response.raise_for_status()
                    with destination.open("wb") as file_handle:
                        async for chunk in response.aiter_bytes():
                            file_handle.write(chunk)
                            bytes_written += len(chunk)
            logger.info(
                "Download attempt succeeded",
                extra={
                    "task_id": task_id,
                    "attempt": attempt,
                    "url_host": url_host,
                    "status_code": status_code,
                    "content_length": content_length,
                    "bytes_written": bytes_written,
                    "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
                },
            )
            return destination
        except (httpx.HTTPError, OSError) as exc:  # pragma: no cover - network dependent
            last_exc = exc
            logger.warning(
                "Download attempt failed",
                extra={
                    "task_id": task_id,
                    "attempt": attempt,
                    "url_host": url_host,
                    "status_code": status_code,
                    "content_length": content_length,
                    "bytes_written": bytes_written,
                    "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
                    "error": str(exc),
                },
            )
            if attempt <= retries:
                backoff = 0.5 * (2 ** (attempt - 1))
                await asyncio.sleep(backoff)
                continue
            break

    timeout_info = (
        f"connect={connect_timeout}s read={read_timeout}s "
        f"write={write_timeout}s pool={pool_timeout}s"
    )
    raise DownloadError(
        f"failed to download raw video after {retries + 1} attempts "
        f"({timeout_info}): {last_exc}"
    )
