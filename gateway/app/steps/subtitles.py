"""Subtitles dispatcher for /v1/subtitles with Gemini as default backend."""

from __future__ import annotations

import asyncio
import os
import logging
import re
import shutil
import subprocess
import time
from pathlib import Path

from fastapi import HTTPException

from gateway.app.config import get_settings
from gateway.app.core.subtitle_utils import preview_lines, segments_to_srt
from gateway.app.core.workspace import (
    Workspace,
    audio_wav_path,
    relative_to_workspace,
    subs_dir,
)
from gateway.app.providers.gemini_subtitles import (
    GeminiSubtitlesError,
    translate_segments_with_gemini,
)
from gateway.app.services import subtitles_openai

logger = logging.getLogger(__name__)


_SRT_TIME_RE = re.compile(
    r"\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}"
)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


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


def _ffmpeg_path() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found in PATH")
    return ffmpeg


def _extract_audio(video_path: Path, wav_path: Path) -> None:
    ffmpeg = _ffmpeg_path()
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(wav_path),
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0 or not wav_path.exists():
        raise RuntimeError(f"ffmpeg audio extract failed: {p.stderr[-800:]}")


def _transcribe_with_faster_whisper(audio_path: Path) -> list[dict]:
    model_name = os.getenv("FASTER_WHISPER_MODEL", "base")
    from faster_whisper import WhisperModel  # type: ignore

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments_iter, _info = model.transcribe(str(audio_path))
    segments = []
    for idx, seg in enumerate(segments_iter, start=1):
        text = (seg.text or "").strip()
        segments.append(
            {
                "index": idx,
                "start": float(seg.start),
                "end": float(seg.end),
                "origin": text,
            }
        )
    return segments


def _parse_srt_to_segments(srt_text: str) -> list[dict]:
    blocks = [b for b in (srt_text or "").split("\n\n") if b.strip()]
    segments = []
    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        time_line = lines[1] if lines[0].strip().isdigit() else lines[0]
        match = _SRT_TIME_RE.search(time_line)
        if not match:
            continue
        start, end = time_line.split("-->")
        start = start.strip()
        end = end.strip()
        start_sec = _parse_srt_time(start)
        end_sec = _parse_srt_time(end)
        text_lines = lines[2:] if lines[0].strip().isdigit() else lines[1:]
        segments.append(
            {
                "index": len(segments) + 1,
                "start": start_sec,
                "end": end_sec,
                "origin": "\n".join(text_lines),
            }
        )
    return segments


def _parse_srt_time(value: str) -> float:
    h, m, rest = value.replace(",", ".").split(":")
    s, ms = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


async def generate_subtitles(
    task_id: str,
    target_lang: str = "my",
    force: bool = False,
    translate_enabled: bool = True,
    use_ffmpeg_extract: bool = True,
) -> dict:
    """Unified subtitles entry point used by the FastAPI route."""

    start_time = time.perf_counter()
    settings = get_settings()
    backend = (settings.subtitles_backend or "").lower()
    asr_backend = settings.asr_backend

    def log_stage(stage: str, **fields) -> None:
        logger.info(
            stage,
            extra={
                "task_id": task_id,
                "step": "subtitles",
                "stage": stage,
                "asr_backend": asr_backend,
                "subtitles_backend": backend,
                "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
                **fields,
            },
        )

    log_stage("SUB2_START")
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
        logger.info(
            "Using Gemini subtitles backend",
            extra={
                "task_id": task_id,
                "raw_exists": workspace.raw_video_exists(),
            },
        )

        segments: list[dict] = []
        if workspace.raw_video_exists():
            wav_path = audio_wav_path(task_id)
            raw_path = workspace.raw_video_path
            raw_size = raw_path.stat().st_size if raw_path.exists() else None
            log_stage(
                "SUB2_WAV_EXTRACT_START",
                raw_path=str(raw_path),
                raw_size=raw_size,
                wav_path=str(wav_path),
            )
            wav_start = time.perf_counter()
            _extract_audio(raw_path, wav_path)
            log_stage(
                "SUB2_WAV_EXTRACT_DONE",
                wav_path=str(wav_path),
                wav_size=wav_path.stat().st_size if wav_path.exists() else None,
                duration_ms=int((time.perf_counter() - wav_start) * 1000),
            )
            asr_start = time.perf_counter()
            log_stage(
                "SUB2_ASR_START",
                wav_path=str(wav_path),
                wav_size=wav_path.stat().st_size if wav_path.exists() else None,
            )
            asr_timeout_sec = _env_int("SUBTITLES_ASR_TIMEOUT_SEC", 600)
            try:
                segments = await asyncio.wait_for(
                    asyncio.to_thread(_transcribe_with_faster_whisper, wav_path),
                    timeout=asr_timeout_sec,
                )
                log_stage(
                    "SUB2_ASR_DONE",
                    segments_count=len(segments),
                    duration_ms=int((time.perf_counter() - asr_start) * 1000),
                )
            except asyncio.TimeoutError:
                log_stage(
                    "SUB2_ASR_FAIL",
                    error="timeout",
                    duration_ms=int((time.perf_counter() - asr_start) * 1000),
                )
                raise HTTPException(status_code=504, detail="ASR timeout")
            except Exception as exc:
                log_stage(
                    "SUB2_ASR_FAIL",
                    error=str(exc),
                    duration_ms=int((time.perf_counter() - asr_start) * 1000),
                )
                raise
        else:
            origin_srt_text = workspace.read_origin_srt_text()
            if not origin_srt_text:
                raise HTTPException(
                    status_code=400,
                    detail="Neither origin.srt nor raw video found, please run /v1/parse first",
                )
            segments = _parse_srt_to_segments(origin_srt_text)

        if not segments:
            raise HTTPException(status_code=502, detail="Whisper transcription returned empty segments")

        origin_text = segments_to_srt(segments, "origin")
        translations: dict[int, str] = {}

        if translate_enabled:
            tr_timeout_sec = _env_int("SUBTITLES_TR_TIMEOUT_SEC", 120)
            tr_retries = _env_int("SUBTITLES_TR_RETRIES", 1)
            for attempt in range(tr_retries + 1):
                tr_start = time.perf_counter()
                log_stage(
                    "SUB2_TR_START",
                    attempt=attempt + 1,
                )
                try:
                    translations = await asyncio.wait_for(
                        asyncio.to_thread(
                            translate_segments_with_gemini,
                            segments=segments,
                            target_lang=target_lang,
                            debug_dir=subs_dir(task_id),
                        ),
                        timeout=tr_timeout_sec,
                    )
                    log_stage(
                        "SUB2_TR_DONE",
                        attempt=attempt + 1,
                        translations_count=len(translations),
                        duration_ms=int((time.perf_counter() - tr_start) * 1000),
                    )
                    break
                except asyncio.TimeoutError:
                    log_stage(
                        "SUB2_TR_FAIL",
                        attempt=attempt + 1,
                        error="timeout",
                        duration_ms=int((time.perf_counter() - tr_start) * 1000),
                    )
                    if attempt < tr_retries:
                        continue
                    translations = {}
                except GeminiSubtitlesError as exc:
                    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
                    retryable = status in (429,) or (isinstance(status, int) and status >= 500)
                    log_stage(
                        "SUB2_TR_FAIL",
                        attempt=attempt + 1,
                        error=str(exc),
                        status_code=status,
                        duration_ms=int((time.perf_counter() - tr_start) * 1000),
                    )
                    if retryable and attempt < tr_retries:
                        continue
                    translations = {}
                except ValueError as exc:
                    log_stage(
                        "SUB2_TR_FAIL",
                        attempt=attempt + 1,
                        error=str(exc),
                        duration_ms=int((time.perf_counter() - tr_start) * 1000),
                    )
                    translations = {}
                break
            if not translations:
                logger.warning("Gemini translation failed; fallback to origin only.")

        for seg in segments:
            idx = int(seg.get("index", 0))
            if idx in translations:
                seg["mm"] = translations[idx]

        mm_text = segments_to_srt(segments, "mm") if translations else ""
        if not mm_text.strip():
            mm_text = origin_text

        scenes_payload = {
            "version": "1.8",
            "language": "origin",
            "segments": segments,
            "scenes": [
                {
                    "scene_id": 1,
                    "start": segments[0]["start"],
                    "end": segments[-1]["end"],
                    "title": "",
                    "mm_title": "",
                }
            ],
        }
        workspace.write_segments_json(scenes_payload)

        origin_srt_path = workspace.write_origin_srt(origin_text)
        mm_srt_path = workspace.write_mm_srt(mm_text)
        origin_txt_path = origin_srt_path.with_suffix(".txt")
        mm_txt_path = mm_srt_path.with_suffix(".txt")
        _write_txt_from_srt(origin_txt_path, origin_text)
        _write_txt_from_srt(mm_txt_path, mm_text)
        log_stage(
            "SUB2_WRITE_DONE",
            origin_srt_path=str(origin_srt_path),
            origin_srt_size=origin_srt_path.stat().st_size if origin_srt_path.exists() else None,
            mm_srt_path=str(mm_srt_path),
            mm_srt_size=mm_srt_path.stat().st_size if mm_srt_path.exists() else None,
            mm_txt_path=str(mm_txt_path),
            mm_txt_size=mm_txt_path.stat().st_size if mm_txt_path.exists() else None,
        )

        logger.info(
            "Subtitles summary",
            extra={
                "task_id": task_id,
                "origin_srt_len": len(origin_text or ""),
                "mm_srt_len": len(mm_text or ""),
                "segments_count": len(segments),
            },
        )
        log_stage(
            "SUB2_DONE",
            origin_srt_len=len(origin_text or ""),
            mm_srt_len=len(mm_text or ""),
            segments_count=len(segments),
        )
        return {
            "task_id": task_id,
            "origin_srt": origin_text,
            "mm_srt": mm_text,
            "mm_txt_path": relative_to_workspace(mm_txt_path),
            "segments_json": scenes_payload,
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
