import subprocess
from pathlib import Path
from typing import Optional

from openai import OpenAI

from gateway.app.config import settings
from gateway.app.core.workspace import subs_dir


class SubtitleError(Exception):
    """Raised when subtitle processing fails."""


def _client() -> OpenAI:
    if not settings.openai_api_key:
        raise SubtitleError("OPENAI_API_KEY is not configured")
    return OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_api_base)


def extract_audio(task_id: str, raw_path: Path) -> Path:
    output = subs_dir() / f"{task_id}.wav"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_path),
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        raise SubtitleError(f"ffmpeg failed: {result.stderr.decode(errors='ignore')}")
    return output


def transcribe(task_id: str, audio_path: Path, force: bool = False) -> Path:
    origin_srt = subs_dir() / f"{task_id}_origin.srt"
    if origin_srt.exists() and not force:
        return origin_srt

    client = _client()
    with audio_path.open("rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model=settings.whisper_model,
            file=audio_file,
            response_format="srt",
        )
    origin_srt.write_text(transcription, encoding="utf-8")
    return origin_srt


def translate(task_id: str, origin_srt: Path, target_lang: str, force: bool = False) -> Path:
    target_suffix = target_lang or "mm"
    target_srt = subs_dir() / f"{task_id}_{target_suffix}.srt"
    if target_srt.exists() and not force:
        return target_srt

    client = _client()
    content = origin_srt.read_text(encoding="utf-8")
    prompt = (
        "Translate the following SRT subtitles into the target language while keeping "
        "the SRT timecodes and numbering. Return only valid SRT text."
    )
    completion = client.chat.completions.create(
        model=settings.gpt_model,
        messages=[
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": f"Target language: {target_lang}\n\nSRT:\n{content}",
            },
        ],
        temperature=0,
    )
    translated = completion.choices[0].message.content or ""
    if not translated.strip():
        raise SubtitleError("translation returned empty content")
    target_srt.write_text(translated, encoding="utf-8")
    return target_srt


def generate_subtitles(
    task_id: str,
    raw_video: Path,
    target_lang: str = "my",
    force: bool = False,
    translate_enabled: bool = True,
) -> dict:
    audio_path = extract_audio(task_id, raw_video)
    origin_srt = transcribe(task_id, audio_path, force=force)
    result: dict[str, Optional[str]] = {
        "audio_path": str(audio_path),
        "origin_srt": str(origin_srt),
        "translated_srt": None,
    }

    if translate_enabled:
        translated_srt = translate(task_id, origin_srt, target_lang, force=force)
        result["translated_srt"] = str(translated_srt)

    return result
