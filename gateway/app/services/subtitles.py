"""Subtitles dispatcher for /v1/subtitles with Gemini as default backend."""

from __future__ import annotations

import logging
from typing import Iterable

from fastapi import HTTPException

from gateway.app.config import get_settings
from gateway.app.core.subtitle_utils import preview_lines
from gateway.app.core.workspace import Workspace
from gateway.app.providers.gemini_subtitles import (
    GeminiSubtitlesError,
    translate_and_segment_with_gemini,
    transcribe_translate_and_segment_with_gemini,
)
from gateway.app.services import subtitles_openai

logger = logging.getLogger(__name__)


def _format_timestamp(seconds: float) -> str:
    milliseconds = max(int(round(seconds * 1000)), 0)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _build_srt_lines(segments: Iterable[dict]) -> tuple[str, str]:
    origin_lines: list[str] = []
    mm_lines: list[str] = []

    for idx, segment in enumerate(segments, start=1):
        seg_index = int(segment.get("index", idx))
        start = float(segment.get("start", 0))
        end = float(segment.get("end", start))
        origin_text = (segment.get("origin") or "").strip()
        mm_text = (segment.get("mm") or origin_text).strip()

        timestamp = f"{_format_timestamp(start)} --> {_format_timestamp(end)}"
        origin_lines.extend([str(seg_index), timestamp, origin_text, ""])
        mm_lines.extend([str(seg_index), timestamp, mm_text, ""])

    origin_srt_text = "\n".join(origin_lines).strip() + "\n"
    mm_srt_text = "\n".join(mm_lines).strip() + "\n"
    return origin_srt_text, mm_srt_text


def build_srt_from_result(
    origin_srt_text: str, result: dict, target_lang: str = "my"
) -> tuple[str, str]:
    segments = result.get("segments") if isinstance(result, dict) else None
    if segments:
        return _build_srt_lines(segments)

    # 如果 Gemini 返回结构中缺少分段，则保底返回原文，并将译文置为空字符串
    return origin_srt_text, ""


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

        origin_text = origin_srt_text or gemini_result.get("origin_srt") or ""
        mm_text = gemini_result.get("mm_srt") or ""

        if not origin_text or not mm_text:
            built_origin, built_mm = build_srt_from_result(
                origin_text or "",
                gemini_result,
                target_lang,
            )
            origin_text = origin_text or built_origin
            mm_text = mm_text or built_mm

        workspace.write_origin_srt(origin_text or "")
        workspace.write_mm_srt(mm_text or "")

        segments_field = gemini_result.get("segments") if isinstance(gemini_result, dict) else None
        segments_count = len(segments_field) if isinstance(segments_field, list) else 0
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
