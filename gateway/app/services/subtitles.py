"""Subtitles dispatcher for /v1/subtitles with Gemini as default backend."""

from __future__ import annotations

import logging
import re

from fastapi import HTTPException

from gateway.app.config import get_settings
from gateway.app.core.subtitle_utils import preview_lines, segments_to_srt
from gateway.app.core.workspace import Workspace, relative_to_workspace, subs_dir
from gateway.app.providers.gemini_subtitles import (
    GeminiSubtitlesError,
    translate_and_segment_with_gemini,
    transcribe_translate_and_segment_with_gemini,
)
from gateway.app.services import subtitles_openai

logger = logging.getLogger(__name__)


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


def _write_txt_from_srt(target_path, srt_text: str) -> None:
    target_path.write_text(_srt_to_txt(srt_text), encoding="utf-8")


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
                    debug_dir=subs_dir(task_id),
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
                    debug_dir=subs_dir(task_id),
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

        origin_srt_path = workspace.write_origin_srt(origin_text)
        mm_srt_path = workspace.write_mm_srt(mm_text)
        origin_txt_path = origin_srt_path.with_suffix(".txt")
        mm_txt_path = mm_srt_path.with_suffix(".txt")
        _write_txt_from_srt(origin_txt_path, origin_text)
        _write_txt_from_srt(mm_txt_path, mm_text)

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
            "mm_txt_path": relative_to_workspace(mm_txt_path),
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
