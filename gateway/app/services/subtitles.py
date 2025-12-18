"""Subtitles dispatcher for /v1/subtitles with Gemini as default backend."""

from __future__ import annotations

import logging

from fastapi import HTTPException

from gateway.app.config import get_settings
from gateway.app.core.subtitle_utils import preview_lines, segments_to_srt
from gateway.app.core.workspace import Workspace
from gateway.app.providers.gemini_subtitles import (
    GeminiSubtitlesError,
    translate_and_segment_with_gemini,
    transcribe_translate_and_segment_with_gemini,
)
from gateway.app.services import subtitles_openai

logger = logging.getLogger(__name__)


def build_preview(text: str | None) -> list[str]:
    if not text:
        return []
    return preview_lines(text)


async def generate_subtitles(
    task_id: str,
    target_lang: str = "my",
    force: bool = False,
    translate_enabled: bool = True,
    use_ffmpeg_extract: bool = True,
) -> dict:
    """Unified subtitles entry point used by the FastAPI route."""

    settings = get_settings()
    backend = (settings.subtitles_backend or "").lower()
    logger.info(
        "Subtitles request started",
        extra={
            "task_id": task_id,
            "asr_backend": settings.asr_backend,
            "subtitles_backend": backend,
        },
    )

    workspace = Workspace(task_id)
    target_lang = target_lang or "my"

    if backend == "gemini":
        origin_srt_text = workspace.read_origin_srt_text()
        logger.info(
            "Using Gemini subtitles backend",
            extra={
                "task_id": task_id,
                "raw_exists": workspace.raw_video_exists(),
                "origin_srt_exists": bool(origin_srt_text),
            },
        )
        try:
            if origin_srt_text:
                gemini_result = translate_and_segment_with_gemini(
                    origin_srt_text=origin_srt_text,
                    target_lang=target_lang,
                )
            else:
                if not workspace.raw_video_exists():
                    raise HTTPException(
                        status_code=400,
                        detail="Neither origin.srt nor raw video found, please run /v1/parse first",
                    )

                gemini_result = transcribe_translate_and_segment_with_gemini(
                    video_path=workspace.raw_video_path,
                    target_lang=target_lang,
                )
                origin_srt_text = gemini_result.get("origin_srt") or origin_srt_text
        except GeminiSubtitlesError as exc:
            msg = str(exc)
            logger.exception("Gemini subtitles failed for %s: %s", task_id, msg)

            if "HTTP 400" in msg or "status_code=400" in msg:
                status_code = 400
            elif "HTTP 429" in msg or "RESOURCE_EXHAUSTED" in msg:
                status_code = 429
                msg = (
                    "Gemini quota / rate limit exceeded. "
                    "Please wait a moment or check your Google/Vertex AI quotas. "
                    f"Raw error: {msg}"
                )
            else:
                status_code = 502

            raise HTTPException(status_code=status_code, detail=msg) from exc

        workspace.write_segments_json(gemini_result)

        segments = gemini_result.get("segments") if isinstance(gemini_result, dict) else []
        origin_text = segments_to_srt(segments or [], "origin") or origin_srt_text or ""
        mm_text = segments_to_srt(segments or [], "mm") or segments_to_srt(
            segments or [], "origin"
        )

        workspace.write_origin_srt(origin_text)
        workspace.write_mm_srt(mm_text)

        segments_count = len(segments) if isinstance(segments, list) else 0
        logger.info(
            "Gemini subtitles summary",
            extra={
                "task_id": task_id,
                "origin_srt_len": len(origin_text or ""),
                "mm_srt_len": len(mm_text or ""),
                "segments_count": segments_count,
            },
        )
        return {
            "task_id": task_id,
            "origin_srt": origin_text,
            "mm_srt": mm_text,
            "segments_json": gemini_result,
            "origin_preview": build_preview(origin_text),
            "mm_preview": build_preview(mm_text),
        }

    if backend == "openai":
        if not settings.openai_api_key:
            raise HTTPException(
                status_code=400,
                detail="OPENAI_API_KEY is not configured for Whisper ASR",
            )

        try:
            return await subtitles_openai.generate_with_openai(
                task_id=task_id,
                target_lang=target_lang,
                force=force,
                translate_enabled=translate_enabled,
                use_ffmpeg_extract=use_ffmpeg_extract,
            )
        except subtitles_openai.SubtitleError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    raise HTTPException(status_code=400, detail=f"Unsupported SUBTITLES_BACKEND: {settings.subtitles_backend}")
