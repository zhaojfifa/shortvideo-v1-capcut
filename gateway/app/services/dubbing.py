from pathlib import Path
import wave

import requests

from gateway.app.config import get_settings
from gateway.app.core.workspace import (
    dubbed_audio_path,
    relative_to_workspace,
    subs_dir,
    translated_srt_path,
)


class DubbingError(Exception):
    """Raised when dubbing fails."""


def _combine_srt_text(srt_path: Path) -> str:
    lines = srt_path.read_text(encoding="utf-8").splitlines()
    text_parts: list[str] = []
    for line in lines:
        if line.strip().isdigit():
            continue
        if "-->" in line:
            continue
        stripped = line.strip()
        if stripped:
            text_parts.append(stripped)
    return " \n".join(text_parts)


def _duration_seconds(wav_path: Path) -> float | None:
    try:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate == 0:
                return None
            return frames / float(rate)
    except Exception:
        return None


def synthesize_voice(task_id: str, target_lang: str, voice_id: str | None = None, force: bool = False) -> dict:
    settings = get_settings()
    translated_srt = translated_srt_path(task_id, target_lang)
    if not translated_srt.exists():
        raise DubbingError("translated subtitles not found; run /v1/subtitles first")

    out_path = dubbed_audio_path(task_id)
    if out_path.exists() and not force:
        duration = _duration_seconds(out_path)
        return {"audio_path": relative_to_workspace(out_path), "duration_sec": duration}

    if not settings.lovo_api_key:
        raise DubbingError("LOVO_API_KEY is not configured")

    text = _combine_srt_text(translated_srt)
    payload = {
        "text": text,
        "voice_id": voice_id or settings.lovo_voice_id_mm,
        "output_format": "wav",
    }
    headers = {"Authorization": f"Bearer {settings.lovo_api_key}"}

    response = requests.post(
        "https://api.lovo.ai/v1/synthesize",
        json=payload,
        headers=headers,
        timeout=60,
    )
    if response.status_code >= 400:
        raise DubbingError(f"LOVO synthesize failed: {response.text}")

    out_path.write_bytes(response.content)
    duration = _duration_seconds(out_path)
    return {"audio_path": relative_to_workspace(out_path), "duration_sec": duration}
