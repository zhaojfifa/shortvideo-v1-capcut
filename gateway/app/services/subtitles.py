"""Subtitle helpers and backend dispatch utilities."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from gateway.app.core.workspace import relative_to_workspace, subs_dir
from gateway.app.services import subtitles_openai as openai_backend
from gateway.app.core.errors import SubtitlesError

logger = logging.getLogger(__name__)


@dataclass
class SubtitleSegment:
    index: int
    start: float  # seconds
    end: float
    origin: str
    mm: str | None = None


def _format_timestamp(seconds: float) -> str:
    total_ms = int(max(seconds, 0) * 1000)
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def segments_to_srt(segments: List[SubtitleSegment], lang: str) -> str:
    """Convert structured segments to an SRT string."""

    lines: list[str] = []
    for idx, seg in enumerate(segments, start=1):
        number = seg.index if seg.index else idx
        start_ts = _format_timestamp(seg.start)
        end_ts = _format_timestamp(seg.end if seg.end is not None else seg.start)
        text = seg.mm if lang == "mm" else seg.origin
        if lang == "mm" and not (text or "").strip():
            text = seg.origin
        text = (text or "").strip()
        lines.extend([str(number), f"{start_ts} --> {end_ts}", text, ""])
    return "\n".join(lines).strip() + "\n"


def preview_lines(text: str, limit: int = 5) -> list[str]:
    lines = [line.strip("\ufeff").rstrip("\n") for line in text.splitlines()]
    preview: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.isdigit() or "-->" in stripped:
            continue
        preview.append(stripped)
        if len(preview) >= limit:
            break
    return preview


async def generate_subtitles_with_whisper(
    settings,
    raw: Path,
    task_id: str,
    target_lang: str = "my",
    force: bool = False,
    translate_enabled: bool = True,
    use_ffmpeg_extract: bool = True,
) -> dict:
    """Existing Whisper/GPT subtitle generation path."""

    if not settings.openai_api_key:
        raise SubtitlesError(
            "OPENAI_API_KEY is not configured; subtitles backend 'openai' is disabled."
        )
    if not raw.exists():
        raise SubtitlesError("raw video not found")

    subs_dir().mkdir(parents=True, exist_ok=True)

    audio_path: Optional[Path] = None
    try:
        if use_ffmpeg_extract:
            origin_srt, audio_path = openai_backend.transcribe_with_ffmpeg(
                task_id, raw, force=force
            )
        else:
            origin_srt = openai_backend.transcribe(task_id, raw, force=force)

        translated_srt: Optional[Path] = None
        if translate_enabled:
            translated_srt = openai_backend.translate(
                task_id, origin_srt, target_lang, force=force
            )
    except Exception as exc:  # pragma: no cover - defensive guard
        raise SubtitlesError(str(exc), cause=exc) from exc

    origin_preview = preview_lines(origin_srt.read_text(encoding="utf-8"))
    mm_preview = (
        preview_lines(translated_srt.read_text(encoding="utf-8"))
        if translated_srt and translated_srt.exists()
        else []
    )

    return {
        "task_id": task_id,
        "backend": "whisper",
        "origin_srt": relative_to_workspace(origin_srt),
        "mm_srt": relative_to_workspace(translated_srt) if translated_srt else None,
        "segments_json": None,
        "wav": relative_to_workspace(audio_path) if audio_path else None,
        "origin_preview": origin_preview,
        "mm_preview": mm_preview,
    }
