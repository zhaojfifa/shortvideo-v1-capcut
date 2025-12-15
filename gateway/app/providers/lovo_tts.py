import logging
from typing import Any, Dict, Optional, Tuple

import requests
from fastapi import HTTPException

from gateway.app.config import get_settings
from gateway.app.settings import settings as app_settings

logger = logging.getLogger(__name__)


VOICE_ID_TO_SPEAKER: dict[str, str | None] = {
    "mm_female_1": app_settings.lovo_speaker_mm_female_1,
}

VOICE_ID_TO_SPEAKER_STYLE: dict[str, str | None] = {
    "mm_female_1": app_settings.lovo_speaker_style_mm_female_1,
}


class LovoTTSError(RuntimeError):
    """Raised when LOVO/Genny synthesis fails."""


def _build_url() -> str:
    settings = get_settings()
    base = (settings.lovo_base_url or "").rstrip("/")
    if not base:
        raise LovoTTSError("LOVO_BASE_URL is not configured")
    return f"{base}/tts/sync"


def resolve_lovo_speaker(voice_id: str | None) -> tuple[str, str | None]:
    """Map UI voice_id to LOVO speaker and style IDs."""

    key = voice_id or "mm_female_1"
    speaker = VOICE_ID_TO_SPEAKER.get(key)
    style = VOICE_ID_TO_SPEAKER_STYLE.get(key)

    if not speaker:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown or unconfigured LOVO voice_id: {key}",
        )

    return speaker, style


def synthesize_sync(
    *,
    text: str,
    voice_id: str | None,
    output_format: str = "wav",
    speed: float = 1.0,
    timeout: int = 120,
) -> Tuple[bytes, str, Optional[str]]:
    """Call the Genny / LOVO sync TTS API and return audio bytes.

    Returns: (audio_content, file_extension, content_type)
    """

    settings = get_settings()
    if not settings.lovo_api_key:
        raise LovoTTSError("LOVO_API_KEY is not configured")

    url = _build_url()
    speaker, speaker_style = resolve_lovo_speaker(voice_id)

    payload: Dict[str, Any] = {
        "text": text,
        "speaker": speaker,
        "speed": speed,
        "format": output_format,
    }
    if speaker_style:
        payload["speakerStyle"] = speaker_style
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": settings.lovo_api_key,
    }

    logger.info(
        "Calling LOVO TTS",
        extra={
            "url": url,
            "voice_id": voice_id,
            "speaker": speaker,
            "format": output_format,
        },
    )
    response = requests.post(url, json=payload, headers=headers, timeout=timeout)
    logger.info("LOVO HTTP %s, preview=%r", response.status_code, response.text[:200])

    if response.status_code >= 400:
        err_msg = response.text[:200]
        try:
            data = response.json()
            if isinstance(data, dict):
                err_msg = data.get("message") or data.get("error") or err_msg
        except Exception:  # pragma: no cover - defensive
            pass
        logger.error("LOVO synthesize failed HTTP %s: %s", response.status_code, err_msg)
        raise LovoTTSError(f"HTTP {response.status_code}: {err_msg}")

    content_type = response.headers.get("Content-Type")
    # Binary audio response
    if content_type and content_type.startswith("audio"):
        ext = "mp3" if "mpeg" in content_type else output_format
        return response.content, ext, content_type

    # JSON response with URL to download
    try:
        data = response.json()
    except Exception as exc:  # pragma: no cover - defensive
        raise LovoTTSError("LOVO synthesize failed: response is not audio or JSON") from exc

    audio_url = _extract_audio_url(data)
    if not audio_url:
        raise LovoTTSError("LOVO synthesize failed: audio URL missing in response")

    try:
        download = requests.get(audio_url, timeout=timeout)
    except requests.RequestException as exc:  # pragma: no cover - network
        raise LovoTTSError("LOVO synthesize failed: download error") from exc

    if download.status_code >= 400:
        logger.error(
            "LOVO synthesize download failed HTTP %s: %s",
            download.status_code,
            download.text[:200],
        )
        raise LovoTTSError(
            f"HTTP {download.status_code}: {download.text[:200]}"
        )

    dl_type = download.headers.get("Content-Type") or content_type
    ext = "mp3" if dl_type and "mpeg" in dl_type else output_format
    return download.content, ext, dl_type


def _extract_audio_url(data: Dict[str, Any]) -> Optional[str]:
    candidates = [
        data.get("url"),
        data.get("audio_url"),
        data.get("result"),
    ]

    if isinstance(data.get("data"), dict):
        inner = data["data"]
        candidates.extend([inner.get("url"), inner.get("audio"), inner.get("audioUrl"), inner.get("result")])

    for value in candidates:
        if isinstance(value, str) and value.startswith("http"):
            return value
    return None
