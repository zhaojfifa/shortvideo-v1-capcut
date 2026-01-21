from __future__ import annotations

import json
from typing import Any

DEFAULT_SUBTITLES_MODE = "whisper+gemini"
DEFAULT_DUB_MODE = "auto-fallback"

_SUBTITLES_MODES = {"whisper-only", "whisper+gemini"}
_DUB_MODES = {"edge", "lovo", "auto-fallback"}


def _pick(value: Any, allowed: set[str], default: str) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    return default


def normalize_pipeline_config(value: Any) -> dict[str, str]:
    """Normalize pipeline_config payload into a stable dict."""

    data: dict[str, Any] = {}
    if isinstance(value, dict):
        data = value
    elif isinstance(value, str):
        text = value.strip()
        if text:
            try:
                decoded = json.loads(text)
            except Exception:
                decoded = None
            if isinstance(decoded, dict):
                data = decoded

    subtitles_mode = _pick(data.get("subtitles_mode"), _SUBTITLES_MODES, DEFAULT_SUBTITLES_MODE)
    dub_mode = _pick(data.get("dub_mode"), _DUB_MODES, DEFAULT_DUB_MODE)
    return {
        "subtitles_mode": subtitles_mode,
        "dub_mode": dub_mode,
    }


def parse_pipeline_config(value: Any) -> dict[str, str]:
    """Parse pipeline_config from storage and apply defaults."""

    return normalize_pipeline_config(value)


def pipeline_config_to_storage(value: Any) -> str | None:
    """Serialize pipeline_config for storage (Text column safe)."""

    if value is None:
        return None
    payload = normalize_pipeline_config(value)
    return json.dumps(payload, ensure_ascii=False)
