from pathlib import Path
import wave

import requests

from gateway.app.config import settings
from gateway.app.core.workspace import audio_dir, subs_dir


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
    translated_srt = subs_dir() / f"{task_id}_{target_lang}.srt"
    if not translated_srt.exists():
        raise DubbingError("translated subtitles not found; run /v1/subtitles first")

    output_dir = audio_dir()
    out_path = output_dir / f"{task_id}_mm_vo.wav"
    if out_path.exists() and not force:
        duration = _duration_seconds(out_path)
        return {"audio_path": str(out_path), "duration_sec": duration}

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
    return {"audio_path": str(out_path), "duration_sec": duration}
