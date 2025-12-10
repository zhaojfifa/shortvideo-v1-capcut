from pathlib import Path

import httpx

from gateway.app.core.workspace import raw_path


class DownloadError(Exception):
    """Raised when raw video download fails."""


async def download_raw_video(task_id: str, url: str) -> Path:
    if not url:
        raise DownloadError("missing download url")

    destination = raw_path(task_id)
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with destination.open("wb") as file_handle:
                    async for chunk in response.aiter_bytes():
                        file_handle.write(chunk)
        except (httpx.HTTPError, OSError) as exc:  # pragma: no cover - network dependent
            raise DownloadError(f"failed to download raw video: {exc}") from exc

    return destination
