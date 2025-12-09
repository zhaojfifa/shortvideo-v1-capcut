"""Douyin parsing service for /v1/parse.

This module is intentionally isolated from subtitles/Gemini logic to avoid
cross-dependencies. It calls the Xiongmao provider to resolve a download URL
and saves the raw video into the workspace.
"""

import logging
from typing import Any, Dict

import httpx
from fastapi import HTTPException

from gateway.app.config import get_settings
from gateway.app.core.workspace import relative_to_workspace
from gateway.app.providers.xiongmao import XiongmaoError, parse_with_xiongmao
from gateway.app.services.download import DownloadError, download_raw_video

logger = logging.getLogger(__name__)


async def parse_douyin_video(task_id: str, link: str) -> Dict[str, Any]:
    """Parse a Douyin link, download the raw video, and return normalized data."""

    settings = get_settings()
    if not settings.douyin_api_base:
        logger.error("DOUYIN_API_BASE is not configured")
        raise HTTPException(status_code=500, detail="DOUYIN_API_BASE is not configured")
    if not settings.douyin_api_key:
        logger.error("DOUYIN_API_KEY is not configured")
        raise HTTPException(status_code=500, detail="DOUYIN_API_KEY is not configured")

    logger.debug(
        "Calling Douyin parser", extra={"task_id": task_id, "link": link, "douyin_api_base": settings.douyin_api_base}
    )

    try:
        parsed = await parse_with_xiongmao(link)
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
