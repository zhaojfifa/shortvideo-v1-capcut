import re
import subprocess
from pathlib import Path
from typing import Optional

from openai import OpenAI

from gateway.app.config import get_settings
from gateway.app.core.workspace import (
    audio_wav_path,
    origin_srt_path,
    raw_input_path,
    relative_to_workspace,
    subs_dir,
    translated_srt_path,
)


class SubtitleError(Exception):
    """Raised when subtitle processing fails."""


_SRT_TIME_RE = re.compile(
    r"\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}"
)


def _srt_to_txt(srt_text: str) -> str:
    blocks = [b for b in srt_text.split("\n\n") if b.strip()]
    lines_out: list[str] = []
    for block in blocks:
        text_lines: list[str] = []
        for line in block.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.isdigit():
                continue
            if "-->" in s or _SRT_TIME_RE.search(s):
                continue
            text_lines.append(s)
        if text_lines:
            lines_out.append(" ".join(text_lines))
    return "\n".join(lines_out).strip() + ("\n" if lines_out else "")


def _write_txt_from_srt(path: Path) -> None:
    srt_text = path.read_text(encoding="utf-8")
    path.with_suffix(".txt").write_text(_srt_to_txt(srt_text), encoding="utf-8")


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


def _client() -> OpenAI:
    settings = get_settings()
    if not settings.openai_api_key:
        raise SubtitleError("OPENAI_API_KEY is not configured")
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_api_base)


def transcribe(task_id: str, raw: Path, force: bool = False) -> Path:
    origin_srt = origin_srt_path(task_id)
    if origin_srt.exists() and not force:
        return origin_srt

    client = _client()
    with raw.open("rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model=get_settings().whisper_model,
            file=audio_file,
            response_format="srt",
        )
    srt_text = transcription.text if hasattr(transcription, "text") else str(transcription)
    origin_srt.write_text(srt_text, encoding="utf-8")
    return origin_srt


def transcribe_with_ffmpeg(task_id: str, raw: Path, force: bool = False) -> tuple[Path, Path]:
    origin_srt = origin_srt_path(task_id)
    wav_path = audio_wav_path(task_id)

    if origin_srt.exists() and wav_path.exists() and not force:
        return origin_srt, wav_path

    wav_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(wav_path),
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="ignore")
        raise SubtitleError(f"ffmpeg failed: {stderr.strip()}")

    client = _client()
    with wav_path.open("rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model=get_settings().whisper_model,
            file=audio_file,
            response_format="srt",
        )
    srt_text = transcription.text if hasattr(transcription, "text") else str(transcription)
    origin_srt.write_text(srt_text, encoding="utf-8")
    return origin_srt, wav_path


def translate(task_id: str, origin_srt: Path, target_lang: str, force: bool = False) -> Path:
    suffix = "mm" if (target_lang or "").lower() in {"my", "mm"} else (target_lang or "mm")
    target_srt = translated_srt_path(task_id, suffix)
    if target_srt.exists() and not force:
        return target_srt

    client = _client()
    content = origin_srt.read_text(encoding="utf-8")
    completion = client.chat.completions.create(
        model=get_settings().gpt_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a subtitle translator. Translate the following SRT subtitles to"
                    f" {target_lang}. "
                    "Keep the SRT structure (indices and timestamps) unchanged, only translate the text lines."
                ),
            },
            {"role": "user", "content": content},
        ],
        temperature=0,
    )
    translated = completion.choices[0].message.content or ""
    if not translated.strip():
        raise SubtitleError("translation returned empty content")
    target_srt.write_text(translated, encoding="utf-8")
    return target_srt


def _preview(path: Path) -> list[str]:
    return preview_lines(path.read_text(encoding="utf-8"))


async def generate_with_openai(
    task_id: str,
    target_lang: str = "my",
    force: bool = False,
    translate_enabled: bool = True,
    use_ffmpeg_extract: bool = False,
) -> dict:
    settings = get_settings()
    if not settings.openai_api_key:
        raise SubtitleError("OPENAI_API_KEY is not configured for Whisper subtitles.")

    raw = raw_input_path(task_id)
    if not raw.exists():
        raise SubtitleError("raw video not found")

    subs_dir(task_id).mkdir(parents=True, exist_ok=True)

    audio_path: Optional[Path] = None

    if use_ffmpeg_extract:
        origin_srt, audio_path = transcribe_with_ffmpeg(task_id, raw, force=force)
    else:
        origin_srt = transcribe(task_id, raw, force=force)

    translated_srt: Optional[Path] = None
    if translate_enabled:
        translated_srt = translate(task_id, origin_srt, target_lang, force=force)
        _write_txt_from_srt(translated_srt)
    _write_txt_from_srt(origin_srt)

    return {
        "task_id": task_id,
        "origin_srt": relative_to_workspace(origin_srt),
        "mm_srt": relative_to_workspace(translated_srt) if translated_srt else None,
        "mm_txt_path": relative_to_workspace(translated_srt.with_suffix(".txt"))
        if translated_srt
        else None,
        "wav": relative_to_workspace(audio_path) if audio_path else None,
        "segments_json": None,
        "origin_preview": _preview(origin_srt),
        "mm_preview": _preview(translated_srt) if translated_srt else [],
    }
