"""Xiongmao short-video parser provider.

This module is responsible for calling the Xiongmao (去水印) API to
resolve download metadata for supported platforms (Douyin/TikTok/XHS).
The function signatures remain stable so downstream services can call
``parse_with_xiongmao`` and receive normalized metadata.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from gateway.app.config import get_settings

logger = logging.getLogger(__name__)


class XiongmaoError(Exception):
    """Raised when the Xiongmao provider fails."""


def _extract_download_url(content: Dict[str, Any]) -> Optional[str]:
    """Pick a usable download URL from the provider content payload."""
    url = content.get("url")
    if url:
        return url

    video_list = content.get("videoList") or []
    if video_list and isinstance(video_list, list):
        first = video_list[0]
        if isinstance(first, dict):
            return first.get("url")
    return None


def _extract_platform(content: Dict[str, Any]) -> str:
    """Derive platform name from provider content if available."""
    return (
        content.get("platform")
        or content.get("ptype")
        or content.get("source")
        or content.get("site")
        or "douyin"
    )


def _normalize_content(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize provider response into the contract used by /v1/parse."""
    content = payload.get("content") or {}
    download_url = _extract_download_url(content)

    return {
        "title": content.get("title"),
        "platform": _extract_platform(content),
        "type": content.get("type") or content.get("workType") or "VIDEO",
        "download_url": download_url,
        "cover": content.get("image") or content.get("cover"),
        "origin_text": content.get("desc") or content.get("title"),
        "raw": content,
    }


def _resolve_settings():
    settings = get_settings()
    # Baseline compatibility: prefer explicit Xiongmao fields when present,
    # fall back to the current douyin_* aliases so both env styles work.
    api_base = getattr(settings, "xiongmao_api_base", None) or getattr(
        settings, "douyin_api_base", ""
    )
    api_key = getattr(settings, "xiongmao_api_key", None) or getattr(
        settings, "douyin_api_key", ""
    )
    app_id = getattr(settings, "xiongmao_app_id", None) or getattr(
        settings, "douyin_app_id", None
    )
    app_id = app_id or "xxmQsyByAk"
    return api_base, api_key, app_id


async def parse_with_xiongmao(link: str) -> Dict[str, Any]:
    """Call Xiongmao API and normalize the response.

    Supports Douyin/TikTok/Xiaohongshu links handled by the provider. This
    implementation keeps the baseline request/response behavior while adding
    gentle validation and logging for easier diagnosis.
    """

    api_base, api_key, app_id = _resolve_settings()
    if not api_base:
        logger.error("Xiongmao API base is not configured")
        raise XiongmaoError("provider error: XIONGMAO_API_BASE is not configured")
    if not api_key:
        logger.error("Xiongmao API key is not configured")
        raise XiongmaoError("provider error: XIONGMAO_API_KEY is not configured")

    url = f"{api_base.rstrip('/')}/waterRemoveDetail/{app_id}"
    params = {"ak": api_key, "link": link}
    logger.debug("Requesting Xiongmao parse", extra={"url": url, "link": link})

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
    except httpx.HTTPError as exc:  # pragma: no cover - network dependent
        logger.exception("Xiongmao provider HTTP error for link %s", link)
        raise XiongmaoError(f"provider error: {exc}") from exc

    try:
        data = response.json()
    except ValueError as exc:  # pragma: no cover - network dependent
        raise XiongmaoError("provider error: invalid json") from exc

    if not isinstance(data, dict):
        raise XiongmaoError("provider error: unexpected response")

    if str(data.get("code")) != "10000":
        message = data.get("msg") or data.get("message") or "短视频解析失败"
        raise XiongmaoError(f"provider error: {message}")

    normalized = _normalize_content(data)
    if not normalized.get("download_url"):
        raise XiongmaoError("provider error: 短视频解析失败，无下载链接")

    return normalized
