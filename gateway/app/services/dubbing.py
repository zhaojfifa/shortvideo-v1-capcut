from pathlib import Path
import wave

from gateway.app.config import get_settings
from gateway.app.core.workspace import Workspace, relative_to_workspace
from gateway.app.providers import lovo_tts


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

    text = _combine_srt_text(srt_text)
    try:
        audio_bytes, ext, _content_type = lovo_tts.synthesize_sync(
            text=text,
            voice_id=voice_id or settings.lovo_voice_id_mm,
            output_format="wav",
        )
    except lovo_tts.LovoTTSError as exc:
        raise DubbingError(str(exc)) from exc

    out_path = ws.write_mm_audio(audio_bytes, suffix=ext or "wav")
    duration = _duration_seconds(out_path)
    return {
        "audio_path": relative_to_workspace(out_path),
        "duration_sec": duration,
        "path": out_path,
    }
