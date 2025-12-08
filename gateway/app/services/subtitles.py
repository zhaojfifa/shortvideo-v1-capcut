"""Subtitle generation backends and helpers."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from gateway.app.core.workspace import (
    relative_to_workspace,
    segments_json_path,
    subs_dir,
    workspace_root,
)

logger = logging.getLogger(__name__)


class SubtitleError(Exception):
    """Raised when subtitle processing fails."""


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
    use_ffmpeg_extract: bool = False,
) -> dict:
    """Existing Whisper/GPT subtitle generation path."""

    if not raw.exists():
        raise SubtitleError("raw video not found")

    subs_dir().mkdir(parents=True, exist_ok=True)

    try:
        from gateway.app.services import subtitles_openai as openai_backend

        audio_path: Optional[Path] = None
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

    except SubtitleError:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise SubtitleError(str(exc)) from exc

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


async def generate_subtitles_with_gemini(settings, raw: Path, task_id: str) -> dict:
    """Gemini-based subtitle generation."""

    if not settings.gemini_api_key:
        raise SubtitleError("GEMINI_API_KEY is not configured")
    if not raw.exists():
        raise SubtitleError("raw video not found")

    try:
        import google.generativeai as genai
    except ImportError as exc:  # pragma: no cover - import guard
        raise SubtitleError("google-generativeai is not installed") from exc

    try:
        genai.configure(api_key=settings.gemini_api_key)
        model_name = settings.gemini_model or "gemini-1.5-flash"
        model = genai.GenerativeModel(model_name)

        prompt = (
            "You are a subtitle engine for short social videos. "
            "Watch this video and produce a JSON object with an array field 'segments'. "
            "Each segment must have: index (int), start_sec (float), end_sec (float), "
            "'origin' (original language text), and 'mm' (Burmese translation). "
            "Keep each line short and suitable for subtitles. Return ONLY valid JSON."
        )

        with raw.open("rb") as f:
            response = model.generate_content(
                [prompt, {"mime_type": "video/mp4", "data": f.read()}],
                generation_config={"response_mime_type": "application/json"},
                stream=False,
            )
    except Exception as exc:  # pragma: no cover - runtime guard
        raise SubtitleError(f"Gemini request failed: {exc}") from exc

    try:
        data = json.loads(getattr(response, "text", ""))
    except Exception:
        logger.exception("Failed to parse Gemini JSON response: %s", getattr(response, "text", ""))
        raise SubtitleError("Gemini returned non-JSON response")

    segments_raw = data.get("segments", []) if isinstance(data, dict) else []
    segments: list[SubtitleSegment] = []
    for seg in segments_raw:
        try:
            segments.append(
                SubtitleSegment(
                    index=int(seg.get("index", len(segments) + 1)),
                    start=float(seg.get("start_sec", seg.get("start", 0) or 0)),
                    end=float(seg.get("end_sec", seg.get("end", 0) or 0)),
                    origin=str(seg.get("origin", seg.get("text_zh", seg.get("text", "")))).strip(),
                    mm=str(seg.get("mm", seg.get("text_my", ""))).strip() or None,
                )
            )
        except Exception:  # pragma: no cover - guard malformed segment
            continue

    subs_dir_path = subs_dir()
    subs_dir_path.mkdir(parents=True, exist_ok=True)

    origin_srt_path = subs_dir_path / f"{task_id}_origin.srt"
    mm_srt_path = subs_dir_path / f"{task_id}_mm.srt"

    origin_srt = segments_to_srt(segments, lang="origin")
    mm_srt = segments_to_srt(segments, lang="mm")

    origin_srt_path.write_text(origin_srt, encoding="utf-8")
    mm_srt_path.write_text(mm_srt, encoding="utf-8")

    scenes_path = segments_json_path(task_id)
    try:
        scenes_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        segments_rel = str(scenes_path.relative_to(workspace_root()))
    except Exception:  # pragma: no cover - writing scenes is optional
        segments_rel = None

    origin_preview = preview_lines(origin_srt)
    mm_preview = preview_lines(mm_srt)

    return {
        "task_id": task_id,
        "backend": "gemini",
        "origin_srt": str(origin_srt_path.relative_to(workspace_root())),
        "mm_srt": str(mm_srt_path.relative_to(workspace_root())),
        "segments_json": segments_rel,
        "wav": None,
        "origin_preview": origin_preview,
        "mm_preview": mm_preview,
    }
