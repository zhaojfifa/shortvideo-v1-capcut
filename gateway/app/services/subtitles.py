"""Subtitle generation backends and helpers."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from gateway.app.core.workspace import (
    relative_to_workspace,
    scenes_json_path,
    subs_dir,
    translated_srt_path,
    workspace_root,
)
from gateway.app.providers.gemini_subtitles import translate_and_segment_with_gemini

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
    use_ffmpeg_extract: bool = True,
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


async def generate_subtitles_with_gemini(
    settings,
    raw: Path,
    task_id: str,
    target_lang: str = "my",
    force: bool = False,
    translate_enabled: bool = True,
    with_scenes: bool = True,
) -> dict:
    """ASR with Whisper + translation/segmentation with Gemini."""

    if not raw.exists():
        raise SubtitleError("raw video not found")

    try:
        from gateway.app.services import subtitles_openai as openai_backend
    except Exception as exc:  # pragma: no cover - defensive import
        raise SubtitleError(str(exc)) from exc

    if not settings.gemini_api_key:
        raise SubtitleError("GEMINI_API_KEY is not configured")

    subs_dir().mkdir(parents=True, exist_ok=True)

    audio_path: Optional[Path] = None
    try:
        origin_srt, audio_path = openai_backend.transcribe_with_ffmpeg(
            task_id, raw, force=force
        )
    except SubtitleError:
        raise
    except Exception as exc:  # pragma: no cover - guard runtime issues
        raise SubtitleError(str(exc)) from exc

    suffix = "mm" if (target_lang or "").lower() in {"my", "mm"} else (target_lang or "mm")
    translated_srt: Optional[Path] = translated_srt_path(task_id, suffix)
    scenes_path = scenes_json_path(task_id)
    segments_rel: Optional[str] = None
    scenes_preview: list = []

    if translated_srt.exists() and not force:
        try:
            if scenes_path.exists():
                segments_rel = str(scenes_path.relative_to(workspace_root()))
                loaded = json.loads(scenes_path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    scenes_preview = loaded[:3]
                elif isinstance(loaded, dict):
                    scenes_preview = (loaded.get("scenes") or [])[:3]
        except Exception:  # pragma: no cover - non-blocking preview
            pass
    elif translate_enabled:
        try:
            translation = translate_and_segment_with_gemini(
                origin_srt.read_text(encoding="utf-8"), target_lang=target_lang or "my"
            )
        except Exception as exc:  # pragma: no cover - external request guard
            raise SubtitleError(f"Gemini translation failed: {exc}") from exc

        segments_raw = translation.get("segments", []) if isinstance(translation, dict) else []
        segments: list[SubtitleSegment] = []
        for seg in segments_raw:
            try:
                segments.append(
                    SubtitleSegment(
                        index=int(seg.get("index", len(segments) + 1)),
                        start=float(seg.get("start") or seg.get("start_sec") or 0),
                        end=float(seg.get("end") or seg.get("end_sec") or 0),
                        origin=str(seg.get("origin", "")).strip(),
                        mm=(str(seg.get("mm", "")).strip() or None),
                    )
                )
            except Exception:  # pragma: no cover - skip malformed segments
                continue

        if segments:
            origin_text = segments_to_srt(segments, lang="origin")
            origin_srt.write_text(origin_text, encoding="utf-8")
            translated_srt.write_text(segments_to_srt(segments, lang="mm"), encoding="utf-8")

        scenes_data = translation.get("scenes") if isinstance(translation, dict) else None
        if with_scenes and scenes_data is not None:
            try:
                payload = translation if isinstance(translation, dict) else scenes_data
                scenes_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                segments_rel = str(scenes_path.relative_to(workspace_root()))
                if isinstance(payload, dict):
                    scenes_preview = (payload.get("scenes") or [])[:3]
                elif isinstance(payload, list):
                    scenes_preview = payload[:3]
            except Exception:  # pragma: no cover - optional scenes persistence
                segments_rel = None

    origin_preview = preview_lines(origin_srt.read_text(encoding="utf-8"))
    mm_preview: list[str] = []
    if translated_srt.exists():
        mm_preview = preview_lines(translated_srt.read_text(encoding="utf-8"))

    return {
        "task_id": task_id,
        "backend": "gemini",
        "origin_srt": str(origin_srt.relative_to(workspace_root())),
        "mm_srt": str(translated_srt.relative_to(workspace_root()))
        if translated_srt and translated_srt.exists()
        else None,
        "segments_json": segments_rel,
        "wav": relative_to_workspace(audio_path) if audio_path else None,
        "origin_preview": origin_preview,
        "mm_preview": mm_preview,
        "scenes_preview": scenes_preview,
    }
