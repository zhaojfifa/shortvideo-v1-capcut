from pathlib import Path
import wave

import requests

from gateway.app.config import get_settings
from gateway.app.core.workspace import Workspace, dubbed_audio_path, relative_to_workspace


class DubbingError(Exception):
    """Raised when dubbing fails."""


def _combine_srt_text(srt_source: Path | str) -> str:
    lines = (
        srt_source.read_text(encoding="utf-8")
        if isinstance(srt_source, Path)
        else str(srt_source)
    ).splitlines()
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


def synthesize_voice(
    task_id: str,
    target_lang: str,
    voice_id: str | None = None,
    force: bool = False,
    mm_srt_text: str | None = None,
    workspace: Workspace | None = None,
) -> dict:
    settings = get_settings()
    ws = workspace or Workspace(task_id)

    if not ws.mm_srt_exists():
        raise DubbingError("translated subtitles not found; run /v1/subtitles first")

    out_path = dubbed_audio_path(task_id)
    if out_path.exists() and not force:
        duration = _duration_seconds(out_path)
        return {"audio_path": relative_to_workspace(out_path), "duration_sec": duration}

    if not settings.lovo_api_key:
        raise DubbingError("LOVO_API_KEY is not configured")

    srt_text = mm_srt_text if mm_srt_text is not None else (ws.read_mm_srt_text() or "")
    if not srt_text.strip():
        raise DubbingError("translated subtitles are empty; please rerun /v1/subtitles")

    text = _combine_srt_text(srt_text)
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
