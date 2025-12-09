"""Subtitle helpers and backend dispatch utilities."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from gateway.app.core.workspace import (
    relative_to_workspace,
    subs_dir,
    origin_srt_path,
    translated_srt_path,
    audio_wav_path,
    raw_path,
)
from gateway.app.services import subtitles_openai as openai_backend
from gateway.app.core.errors import SubtitlesError
from gateway.app.config import get_settings

import subprocess
import json
try:
    from google import genai
except Exception:
    genai = None
import openai

logger = logging.getLogger(__name__)


@dataclass
class SubtitleSegment:
    index: int
    start: float  # seconds
    end: float
    origin: str
    mm: str | None = None


def _format_timestamp(seconds: float) -> str:
    total_ms = int(max(seconds, 0) * 1000)
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def segments_to_srt(segments: List[SubtitleSegment], lang: str) -> str:
    """Convert structured segments to an SRT string."""

    lines: list[str] = []
    for idx, seg in enumerate(segments, start=1):
        number = seg.index if seg.index else idx
        start_ts = _format_timestamp(seg.start)
        end_ts = _format_timestamp(seg.end if seg.end is not None else seg.start)
        text = seg.mm if lang == "mm" else seg.origin
        if lang == "mm" and not (text or "").strip():
            text = seg.origin
        text = (text or "").strip()
        lines.extend([str(number), f"{start_ts} --> {end_ts}", text, ""])
    return "\n".join(lines).strip() + "\n"


from gateway.app.core.subtitle_utils import preview_lines


async def generate_subtitles_with_whisper(
    settings,
    raw: Path,
    task_id: str,
    target_lang: str = "my",
    force: bool = False,
    translate_enabled: bool = True,
    use_ffmpeg_extract: bool = True,
) -> dict:
    """Existing Whisper/GPT subtitle generation path."""

    if not settings.openai_api_key:
        raise SubtitlesError(
            "OPENAI_API_KEY is not configured; subtitles backend 'openai' is disabled."
        )
    if not raw.exists():
        raise SubtitlesError("raw video not found")

    subs_dir().mkdir(parents=True, exist_ok=True)

    audio_path: Optional[Path] = None
    try:
        if use_ffmpeg_extract:
            origin_srt, audio_path = openai_backend.transcribe_with_ffmpeg(
                task_id, raw, force=force
            )
        else:
            origin_srt = openai_backend.transcribe(task_id, raw, force=force)

        translated_srt: Optional[Path] = None
        if translate_enabled:
            translated_srt = openai_backend.translate(
                task_id, origin_srt, target_lang, force=force
            )
    except Exception as exc:  # pragma: no cover - defensive guard
        raise SubtitlesError(str(exc), cause=exc) from exc

    origin_preview = preview_lines(origin_srt.read_text(encoding="utf-8"))
    mm_preview = (
        preview_lines(translated_srt.read_text(encoding="utf-8"))
        if translated_srt and translated_srt.exists()
        else []
    )

    return {
        "task_id": task_id,
        "backend": "whisper",
        "origin_srt": relative_to_workspace(origin_srt),
        "mm_srt": relative_to_workspace(translated_srt) if translated_srt else None,
        "segments_json": None,
        "wav": relative_to_workspace(audio_path) if audio_path else None,
        "origin_preview": origin_preview,
        "mm_preview": mm_preview,
    }


async def _generate_with_gemini(
    settings,
    raw: Path,
    task_id: str,
    target_lang: str = "my",
    force: bool = False,
    translate_enabled: bool = True,
    use_ffmpeg_extract: bool = True,
) -> dict:
    """Minimal Gemini-based subtitles generator.

    说明 (中文注释):
    - 将视频转为 WAV (存放在 edits/subs/)
    - 使用 google.generativeai (genai.Client) 上传音频并请求纯文本转录
    - 根据转录结果简单生成一个 SRT（单条或多条），并保存到 edits/subs/
    """

    if not settings.gemini_api_key:
        raise SubtitlesError("GEMINI_API_KEY is not configured")

    if genai is None:
        raise SubtitlesError("google-generativeai is not installed")

    if not raw.exists():
        raise SubtitlesError("raw video not found")

    subs_dir().mkdir(parents=True, exist_ok=True)
    wav_path = audio_wav_path(task_id)
    origin_srt = origin_srt_path(task_id)
    mm_srt = translated_srt_path(task_id, "mm")

    # extract audio with ffmpeg
    if force or not wav_path.exists():
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(raw),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(wav_path),
        ]
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="ignore")
            raise SubtitlesError(f"ffmpeg failed: {stderr.strip()}")

    # call Gemini / genai to transcribe audio
    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        model = settings.gemini_model or "gemini-2.0-flash"
        with wav_path.open("rb") as f:
            resp = client.models.generate_content(
                model=model,
                contents=["Transcribe the following audio:", {"mime_type": "audio/wav", "data": f.read()}],
                config={"response_mime_type": "text/plain"},
            )
    except Exception as exc:
        raise SubtitlesError(f"Gemini request failed: {exc}") from exc

    text = getattr(resp, "text", "") or ""
    if not text.strip():
        raise SubtitlesError("Gemini returned empty transcription")

    # Try to determine duration via ffprobe to create a simple SRT timestamp
    duration = None
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(wav_path),
            ],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            duration = float(probe.stdout.strip() or 0.0)
    except Exception:
        duration = None

    # Build a very simple SRT: single segment covering full duration (or 10s fallback)
    end_sec = duration or 10.0
    start_ts = _format_timestamp(0.0)
    end_ts = _format_timestamp(end_sec)
    srt_text = f"1\n{start_ts} --> {end_ts}\n{text.strip()}\n\n"

    origin_srt.write_text(srt_text, encoding="utf-8")
    mm_srt.write_text(srt_text, encoding="utf-8")

    origin_preview = preview_lines(srt_text)

    return {
        "task_id": task_id,
        "backend": "gemini",
        "origin_srt": relative_to_workspace(origin_srt),
        "mm_srt": relative_to_workspace(mm_srt),
        "segments_json": None,
        "wav": relative_to_workspace(wav_path),
        "origin_preview": origin_preview,
        "mm_preview": origin_preview,
    }


async def generate_subtitles(
    settings,
    raw: Path,
    task_id: str,
    target_lang: str = "my",
    force: bool = False,
    translate_enabled: bool = True,
    use_ffmpeg_extract: bool = True,
) -> dict:
    """Unified entrypoint: 根据 settings.subtitles_backend 路由到 openai 或 gemini 实现。

    说明(中文注释):
    - 避免服务层引用 app.main 或 router，错误类型统一来自 core.errors
    - 捕获 OpenAI 的 rate limit (429) 并封装成 SubtitlesError
    """

    backend = (getattr(settings, "subtitles_backend", "openai") or "openai").lower()
    if backend == "openai":
        try:
            return await generate_subtitles_with_whisper(
                settings,
                raw,
                task_id,
                target_lang=target_lang,
                force=force,
                translate_enabled=translate_enabled,
                use_ffmpeg_extract=use_ffmpeg_extract,
            )
        except Exception as exc:
            # OpenAI specific rate-limit handling
            try:
                # openai library exposes RateLimitError
                from openai.error import RateLimitError

                if isinstance(exc, RateLimitError):
                    raise SubtitlesError("OpenAI rate limit (429): insufficient quota or request throttled") from exc
            except Exception:
                pass
            # inspect for HTTP status attr
            if getattr(exc, "http_status", None) == 429 or "429" in str(exc):
                raise SubtitlesError("OpenAI rate limit (429): insufficient quota or request throttled") from exc
            raise SubtitlesError(str(exc), cause=exc) from exc
    elif backend == "gemini":
        return await _generate_with_gemini(
            settings, raw, task_id, target_lang, force, translate_enabled, use_ffmpeg_extract
        )
    else:
        raise SubtitlesError(f"Unknown subtitles backend: {backend}")
