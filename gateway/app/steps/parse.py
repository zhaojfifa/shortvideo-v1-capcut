"""Douyin parsing service for /v1/parse.

This module is intentionally isolated from subtitles/Gemini logic to avoid
cross-dependencies. It calls the Xiongmao provider to resolve a download URL
and saves the raw video into the workspace.
"""

import logging
import re
from typing import Any, Dict, Optional

from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from gateway.app.core.workspace import relative_to_workspace
from gateway.app.providers.xiongmao import XiongmaoError, parse_with_xiongmao
from gateway.app.services.download import DownloadError, download_raw_video

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"(https?://[^\s]+)")
_IESDOUYIN_RE = re.compile(
    r"https?://(?:www\.)?iesdouyin\.com/share/video/(\d+)",
    re.IGNORECASE,
)


def _validate_url(url: str) -> str:
    if not url or not str(url).strip():
        raise ValueError("Invalid video URL: empty input")
    text = str(url).strip()
    match = _URL_RE.search(text)
    candidate = match.group(1) if match else text
    candidate = candidate.rstrip(",.\"\'] ")
    ies_match = _IESDOUYIN_RE.search(candidate)
    if ies_match:
        candidate = f"https://www.douyin.com/video/{ies_match.group(1)}"
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid video URL: {url}")
    return candidate


def _normalize_platform(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    lowered = str(value).strip().lower()
    if lowered == "tk":
        return "tiktok"
    if lowered == "fb":
        return "facebook"
    return lowered


def detect_platform(url: str, explicit: Optional[str] = None) -> str:
    if explicit and explicit != "auto":
        return _normalize_platform(explicit) or explicit

    lowered = url.lower()
    if "douyin.com" in lowered:
        return "douyin"
    if "tiktok.com" in lowered:
        return "tiktok"
    if "xiaohongshu.com" in lowered or "xhslink.com" in lowered:
        return "xhs"
    if "facebook.com" in lowered or "fb.watch" in lowered:
        return "facebook"

    raise ValueError(f"Cannot detect platform from url: {url}")


async def parse_video(
    task_id: str,
    link: str,
    platform_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Parse a video link, download the raw video, and return normalized data."""

    try:
        normalized_link = _validate_url(link)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.debug(
        "Calling parse provider",
        extra={"task_id": task_id, "link": normalized_link},
    )

    try:
        parsed = await parse_with_xiongmao(normalized_link)
    except httpx.HTTPError as exc:  # pragma: no cover - network dependent
        logger.exception("Parse failed for %s", link)
        raise HTTPException(status_code=502, detail=f"Parse failed: {exc}") from exc
    except XiongmaoError as exc:
        logger.exception("Xiongmao provider error for %s", link)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected error during parse for %s", link)
        raise HTTPException(status_code=500, detail="Unexpected parse error") from exc

    try:
        raw_file = await download_raw_video(task_id, parsed.get("download_url") or "")
    except DownloadError as exc:
        logger.exception("Failed downloading raw video for task %s", task_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected download error for task %s", task_id)
        raise HTTPException(status_code=500, detail="Failed to download raw video") from exc

    detected_platform = None
    try:
        detected_platform = detect_platform(normalized_link, platform_hint)
    except ValueError:
        detected_platform = None

    platform_value = detected_platform or _normalize_platform(platform_hint) or "unknown"

    return {
        "task_id": task_id,
        "platform": platform_value,
        "title": parsed.get("title"),
        "type": parsed.get("type") or "VIDEO",
        "download_url": parsed.get("download_url"),
        "cover": parsed.get("cover"),
        "origin_text": parsed.get("origin_text"),
        "raw": parsed.get("raw"),
        "raw_exists": raw_file.exists(),
        "raw_path": relative_to_workspace(raw_file),
    }


async def parse_douyin_video(task_id: str, link: str) -> Dict[str, Any]:
    """Parse a Douyin link, download the raw video, and return normalized data."""

    return await parse_video(task_id, link, platform_hint="douyin")
