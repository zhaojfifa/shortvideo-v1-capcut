import httpx

from gateway.app.config import get_settings


class XiongmaoError(Exception):
    """Raised when the Xiongmao provider fails."""


def _extract_download_url(content: dict) -> str | None:
    url = content.get("url")
    if url:
        return url
    video_list = content.get("videoList") or []
    if video_list and isinstance(video_list, list):
        candidate = video_list[0]
        return candidate.get("url") if isinstance(candidate, dict) else None
    return None


def _normalize_content(payload: dict) -> dict:
    content = payload.get("content") or {}
    download_url = _extract_download_url(content)
    return {
        "title": content.get("title"),
        "type": content.get("type") or content.get("workType") or "VIDEO",
        "download_url": download_url,
        "cover": content.get("image") or content.get("cover"),
        "origin_text": content.get("desc") or content.get("title"),
        "raw": content,
    }


async def parse_with_xiongmao(link: str) -> dict:
    settings = get_settings()
    app_id = "xxmQsyByAk"
    params = {
        "ak": settings.douyin_api_key,
        "link": link,
    }
    url = f"{settings.douyin_api_base}/waterRemoveDetail/{app_id}"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(url, params=params)
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
