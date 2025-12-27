"""Douyin parsing service for /v1/parse.

This module is intentionally isolated from subtitles/Gemini logic to avoid
cross-dependencies. It calls the Xiongmao provider to resolve a download URL
and saves the raw video into the workspace.
"""

import logging
from typing import Any, Dict, Optional

from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from gateway.app.core.workspace import relative_to_workspace
from gateway.app.providers.xiongmao import XiongmaoError, parse_with_xiongmao
from gateway.app.services.download import DownloadError, download_raw_video

logger = logging.getLogger(__name__)


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid video URL: {url}")
    return url


def detect_platform(url: str, explicit: Optional[str] = None) -> str:
    if explicit and explicit != "auto":
        return explicit

    lowered = url.lower()
    if "douyin.com" in lowered:
        return "douyin"
    if "xiaohongshu.com" in lowered or "xhslink.com" in lowered:
        return "xhs"

    raise ValueError(f"Cannot detect platform from url: {url}")


async def parse_douyin_video(task_id: str, link: str) -> Dict[str, Any]:
    """Parse a Douyin link, download the raw video, and return normalized data."""

    try:
        normalized_link = _validate_url(link)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.debug(
        "Calling Douyin parser",
        extra={"task_id": task_id, "link": normalized_link},
    )

    try:
        parsed = await parse_with_xiongmao(normalized_link)
    except httpx.HTTPError as exc:  # pragma: no cover - network dependent
        logger.exception("Douyin parse failed for %s", link)
        raise HTTPException(status_code=502, detail=f"Douyin parse failed: {exc}") from exc
    except XiongmaoError as exc:
        logger.exception("Xiongmao provider error for %s", link)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected error during Douyin parse for %s", link)
        raise HTTPException(status_code=500, detail="Unexpected Douyin parse error") from exc

    try:
        raw_file = await download_raw_video(task_id, parsed.get("download_url") or "")
    except DownloadError as exc:
        logger.exception("Failed downloading raw video for task %s", task_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected download error for task %s", task_id)
        raise HTTPException(status_code=500, detail="Failed to download raw video") from exc

    return {
        "task_id": task_id,
        "platform": "douyin",
        "title": parsed.get("title"),
        "type": parsed.get("type") or "VIDEO",
        "download_url": parsed.get("download_url"),
        "cover": parsed.get("cover"),
        "origin_text": parsed.get("origin_text"),
        "raw": parsed.get("raw"),
        "raw_exists": raw_file.exists(),
        "raw_path": relative_to_workspace(raw_file),
    }
