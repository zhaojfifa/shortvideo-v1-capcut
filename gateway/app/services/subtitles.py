import subprocess
from pathlib import Path
from typing import Optional

from openai import OpenAI

from gateway.app.config import settings
from gateway.app.core.workspace import (
    origin_srt_path,
    relative_to_workspace,
    subs_dir,
    translated_srt_path,
)


class SubtitleError(Exception):
    """Raised when subtitle processing fails."""


def _client() -> OpenAI:
    if not settings.openai_api_key:
        raise SubtitleError("OPENAI_API_KEY is not configured")
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_api_base)


def transcribe(task_id: str, raw_path: Path, force: bool = False) -> Path:
    origin_srt = origin_srt_path(task_id)
    if origin_srt.exists() and not force:
        return origin_srt

    client = _client()
    with raw_path.open("rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model=settings.whisper_model,
            file=audio_file,
            response_format="srt",
        )
    srt_text = transcription.text if hasattr(transcription, "text") else str(transcription)
    origin_srt.write_text(srt_text, encoding="utf-8")
    return origin_srt


def transcribe_with_ffmpeg(task_id: str, raw_path: Path, force: bool = False) -> tuple[Path, Path]:
    origin_srt = origin_srt_path(task_id)
    wav_path = subs_dir() / f"{task_id}.wav"

    if origin_srt.exists() and wav_path.exists() and not force:
        return origin_srt, wav_path

    wav_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_path),
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
            model=settings.whisper_model,
            file=audio_file,
            response_format="srt",
        )
    srt_text = transcription.text if hasattr(transcription, "text") else str(transcription)
    origin_srt.write_text(srt_text, encoding="utf-8")
    return origin_srt, wav_path


def translate(task_id: str, origin_srt: Path, target_lang: str, force: bool = False) -> Path:
    target_srt = translated_srt_path(task_id, target_lang)
    if target_srt.exists() and not force:
        return target_srt

    client = _client()
    content = origin_srt.read_text(encoding="utf-8")
    completion = client.chat.completions.create(
        model=settings.gpt_model,
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


def _preview_lines(path: Path, limit: int = 5) -> list[str]:
    lines = [line.strip("\ufeff").rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines()]
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


def generate_subtitles(
    task_id: str,
    raw_video: Path,
    target_lang: str = "my",
    force: bool = False,
    translate_enabled: bool = True,
    use_ffmpeg_extract: bool = False,
) -> dict:
    if not raw_video.exists():
        raise SubtitleError("raw video not found")

    audio_path: Optional[Path] = None

    if use_ffmpeg_extract:
        origin_srt, audio_path = transcribe_with_ffmpeg(task_id, raw_video, force=force)
    else:
        origin_srt = transcribe(task_id, raw_video, force=force)

    result: dict[str, Optional[str] | list[str]] = {
        "audio_path": relative_to_workspace(audio_path) if audio_path else None,
        "origin_srt": relative_to_workspace(origin_srt),
        "translated_srt": None,
        "origin_preview": _preview_lines(origin_srt),
        "translated_preview": None,
    }

    if translate_enabled:
        translated_srt = translate(task_id, origin_srt, target_lang, force=force)
        result["translated_srt"] = relative_to_workspace(translated_srt)
        result["translated_preview"] = _preview_lines(translated_srt)

    return result
