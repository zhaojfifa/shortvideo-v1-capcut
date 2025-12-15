import json
import logging
from pathlib import Path
import wave

from gateway.app.config import get_settings
from gateway.app.core.workspace import Workspace, relative_to_workspace
from gateway.app.providers import lovo_tts


logger = logging.getLogger(__name__)


LOVO_MAX_CHARS = 480  # stay safely below LOVO's 500-char per-block limit


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


def _truncate_lovo_script(text: str) -> str:
    """Ensure text fits within LOVO's 500-character block limit."""

    full_script = text.strip()
    if len(full_script) <= LOVO_MAX_CHARS:
        return full_script

    cut = full_script.rfind("။", 0, LOVO_MAX_CHARS)
    if cut == -1:
        cut = full_script.rfind(".", 0, LOVO_MAX_CHARS)
    if cut == -1:
        cut = LOVO_MAX_CHARS

    truncated = full_script[:cut].rstrip()
    logger.warning(
        "Truncating LOVO dubbing script from %d to %d chars due to LOVO limit",
        len(full_script),
        len(truncated),
    )
    return truncated


def build_lovo_script_from_segments(segments: list[dict]) -> str:
    """
    Build a dubbing script from translated segments and enforce LOVO's length cap.

    For now we concatenate the target-language strings and trim to a single
    block suitable for LOVO /tts/sync.
    """

    parts: list[str] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        text = (
            seg.get("target_text")
            or seg.get("mm_text")
            or seg.get("mm")
            or seg.get("target")
            or ""
        ).strip()
        if not text:
            continue
        parts.append(text)

    full_script = " ".join(parts).strip()
    if not full_script:
        return ""

    return _truncate_lovo_script(full_script)


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

    if ws.mm_audio_exists() and not force:
        out_path = ws.mm_audio_path
        duration = _duration_seconds(out_path)
        return {
            "audio_path": relative_to_workspace(out_path),
            "duration_sec": duration,
            "path": out_path,
        }

    srt_text = mm_srt_text if mm_srt_text is not None else (ws.read_mm_srt_text() or "")
    if not srt_text.strip():
        raise DubbingError("translated subtitles are empty; please rerun /v1/subtitles")

    segments: list[dict] = []
    if ws.segments_json.exists():
        try:
            raw = json.loads(ws.segments_json.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                segments = raw.get("segments") or raw.get("data") or []
                if isinstance(segments, dict):
                    segments = segments.get("segments", [])
            elif isinstance(raw, list):
                segments = raw
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load segments JSON for %s: %s", task_id, exc)

    script = build_lovo_script_from_segments(segments) if segments else ""
    if not script:
        script = _truncate_lovo_script(_combine_srt_text(srt_text))

    try:
        audio_bytes, ext, _content_type = lovo_tts.synthesize_sync(
            text=script,
            voice_id=voice_id or settings.lovo_voice_id_mm,
            output_format="wav",
        )
    except lovo_tts.LovoTTSError as exc:
        raise DubbingError(f"LOVO synthesize failed: {exc}") from exc

    out_path = ws.write_mm_audio(audio_bytes, suffix=ext or "wav")
    duration = _duration_seconds(out_path)
    return {
        "audio_path": relative_to_workspace(out_path),
        "duration_sec": duration,
        "path": out_path,
    }
