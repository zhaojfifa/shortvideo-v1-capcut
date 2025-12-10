"""Gemini-only subtitles dispatcher used by /v1/subtitles."""
"""Gemini-only subtitles dispatcher used by /v1/subtitles."""

import logging
from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from gateway.app.config import get_settings
from gateway.app.core.workspace import (
    audio_wav_path,
    origin_srt_path,
    raw_path,
    relative_to_workspace,
    subs_dir,
    translated_srt_path,
)
from gateway.app.services.gemini_subtitles import transcribe_and_translate_with_gemini
from gateway.app.services import subtitles_openai

logger = logging.getLogger(__name__)

SubtitleError = subtitles_openai.SubtitleError
preview_lines = subtitles_openai.preview_lines


async def generate_subtitles_with_whisper(
    raw: Path,
    task_id: str,
    target_lang: str = "my",
    force: bool = False,
    use_ffmpeg_extract: bool = True,
) -> dict:
    """Run Whisper ASR (OpenAI) to produce origin subtitles and optional wav."""

    settings = get_settings()
    if not settings.openai_api_key:
        raise SubtitleError("OPENAI_API_KEY is not configured for Whisper ASR")
    if not raw.exists():
        raise SubtitleError("raw video not found")

    subs_dir().mkdir(parents=True, exist_ok=True)

    audio_path: Optional[Path] = None
    try:
        if use_ffmpeg_extract:
            origin_srt, audio_path = subtitles_openai.transcribe_with_ffmpeg(
                task_id, raw, force=force
            )
        else:
            origin_srt = subtitles_openai.transcribe(task_id, raw, force=force)
    except Exception as exc:  # pragma: no cover - defensive
        raise SubtitleError(str(exc)) from exc

    origin_preview = preview_lines(origin_srt.read_text(encoding="utf-8"))

    return {
        "task_id": task_id,
        "origin_srt": relative_to_workspace(origin_srt),
        "mm_srt": None,
        "segments_json": None,
        "wav": relative_to_workspace(audio_path) if audio_path else None,
        "origin_preview": origin_preview,
        "mm_preview": [],
    }


async def generate_subtitles(
    task_id: str,
    target_lang: str = "my",
    force: bool = False,
    translate_enabled: bool = True,
    use_ffmpeg_extract: bool = True,
) -> dict:
    """Unified Gemini subtitles entry point used by the FastAPI route."""

    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not configured; subtitles backend 'gemini' is disabled.",
        )

    raw_file = raw_path(task_id)
    if not raw_file.exists():
        raise HTTPException(status_code=400, detail="raw video not found")

    try:
        whisper_result = await generate_subtitles_with_whisper(
            raw_file,
            task_id,
            target_lang=target_lang,
            force=force,
            use_ffmpeg_extract=use_ffmpeg_extract,
        )
    except SubtitleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    origin_path = origin_srt_path(task_id)
    origin_text = origin_path.read_text(encoding="utf-8")

    mm_path = translated_srt_path(task_id, "mm")

    origin_result = origin_text
    mm_result: Optional[str] = None
    if translate_enabled:
        try:
            origin_result, mm_result = await transcribe_and_translate_with_gemini(
                origin_text, target_lang=target_lang or "my"
            )
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover - defensive external call
            logger.exception("Gemini subtitles failed")
            raise HTTPException(status_code=502, detail="Gemini subtitles failed") from exc

        mm_result = (mm_result or "").strip()
        mm_path.write_text(mm_result, encoding="utf-8")

    wav_path = audio_wav_path(task_id)

    return {
        "task_id": task_id,
        "origin_srt": relative_to_workspace(origin_path),
        "mm_srt": relative_to_workspace(mm_path) if mm_result else None,
        "wav": relative_to_workspace(wav_path) if wav_path.exists() else None,
        "segments_json": None,
        "origin_preview": whisper_result.get("origin_preview") or preview_lines(
            origin_result
        ),
        "mm_preview": preview_lines(mm_result) if mm_result else [],
        "scenes_preview": [],
    }
