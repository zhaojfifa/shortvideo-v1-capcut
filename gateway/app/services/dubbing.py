"""
Compatibility shim for legacy imports: gateway.app.services.dubbing

IMPORTANT:
- Do NOT implement dubbing logic here.
- Route to v1.62+ step/usecase that reads subtitles.json (SSOT).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any

from gateway.app.config import get_settings
from gateway.app.core.workspace import Workspace
from gateway.app.providers.edge_tts import EdgeTTSError, generate_audio_edge_tts
from gateway.app.providers import lovo_tts

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class DubbingError(RuntimeError):
    """Raised when dubbing synthesis fails."""


_SRT_TIME_RE = re.compile(
    r"\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}"
)


def _srt_to_text(srt_text: str) -> str:
    blocks = [b for b in srt_text.split("\n\n") if b.strip()]
    lines_out: list[str] = []
    for block in blocks:
        for line in block.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.isdigit():
                continue
            if "-->" in s or _SRT_TIME_RE.search(s):
                continue
            lines_out.append(s)
    return " ".join(lines_out).strip()


def _normalize_text(mm_srt_text: str) -> str:
    if not mm_srt_text:
        return ""
    if _SRT_TIME_RE.search(mm_srt_text):
        return _srt_to_text(mm_srt_text)
    return mm_srt_text.strip()


def _map_edge_voice_id(voice_id: str | None, settings) -> str:
    voice_key = voice_id or "mm_female_1"
    return settings.edge_tts_voice_map.get(voice_key, voice_key)


async def _synthesize_from_text(
    *,
    task_id: str,
    target_lang: str | None,
    voice_id: str | None,
    force: bool,
    mm_srt_text: str,
    workspace: Workspace | None,
) -> dict:
    ws = workspace or Workspace(task_id)
    if ws.mm_audio_exists() and not force:
        return {"audio_path": str(ws.mm_audio_path), "duration_sec": None}

    start_time = time.perf_counter()
    text = _normalize_text(mm_srt_text)
    if not text:
        raise DubbingError("Empty text for dubbing")

    settings = get_settings()
    provider = (settings.dub_provider or "edge-tts").lower()
    if provider == "edge":
        provider = "edge-tts"

    tts_timeout_sec = _env_int("DUB_TTS_TIMEOUT_SEC", 300)

    if provider == "edge-tts":
        voice = _map_edge_voice_id(voice_id, settings)
        output_path = ws.mm_audio_mp3_path
        logger.info(
            "DUB3_TTS_START",
            extra={
                "task_id": task_id,
                "step": "dub",
                "stage": "DUB3_TTS_START",
                "dub_provider": provider,
                "voice_id": voice_id,
                "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
                "output_path": str(output_path),
                "text_len": len(text),
                "timeout_sec": tts_timeout_sec,
            },
        )
        try:
            await asyncio.wait_for(
                generate_audio_edge_tts(text, voice, str(output_path)),
                timeout=tts_timeout_sec,
            )
        except EdgeTTSError as exc:
            logger.info(
                "DUB3_TTS_FAIL",
                extra={
                    "task_id": task_id,
                    "step": "dub",
                    "stage": "DUB3_TTS_FAIL",
                    "dub_provider": provider,
                    "voice_id": voice_id,
                    "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
                    "error": str(exc),
                },
            )
            raise DubbingError(str(exc)) from exc
        except asyncio.TimeoutError:
            logger.info(
                "DUB3_TTS_FAIL",
                extra={
                    "task_id": task_id,
                    "step": "dub",
                    "stage": "DUB3_TTS_FAIL",
                    "dub_provider": provider,
                    "voice_id": voice_id,
                    "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
                    "error": "timeout",
                },
            )
            raise DubbingError("Edge-TTS timeout")
        except Exception as exc:
            logger.info(
                "DUB3_TTS_FAIL",
                extra={
                    "task_id": task_id,
                    "step": "dub",
                    "stage": "DUB3_TTS_FAIL",
                    "dub_provider": provider,
                    "voice_id": voice_id,
                    "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
                    "error": str(exc),
                },
            )
            raise DubbingError(f"Edge-TTS failed: {exc}") from exc
        if not output_path.exists():
            logger.info(
                "DUB3_TTS_FAIL",
                extra={
                    "task_id": task_id,
                    "step": "dub",
                    "stage": "DUB3_TTS_FAIL",
                    "dub_provider": provider,
                    "voice_id": voice_id,
                    "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
                    "error": "output_missing",
                },
            )
            raise DubbingError("Edge-TTS did not produce audio output")
        logger.info(
            "DUB3_TTS_DONE",
            extra={
                "task_id": task_id,
                "step": "dub",
                "stage": "DUB3_TTS_DONE",
                "dub_provider": provider,
                "voice_id": voice_id,
                "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
                "output_path": str(output_path),
                "output_size": output_path.stat().st_size if output_path.exists() else None,
            },
        )
        return {"audio_path": str(output_path), "duration_sec": None}

    if provider == "lovo":
        logger.info(
            "DUB3_TTS_START",
            extra={
                "task_id": task_id,
                "step": "dub",
                "stage": "DUB3_TTS_START",
                "dub_provider": provider,
                "voice_id": voice_id,
                "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
                "text_len": len(text),
                "timeout_sec": tts_timeout_sec,
            },
        )
        try:
            content, ext, _ = await asyncio.wait_for(
                asyncio.to_thread(
                    lovo_tts.synthesize_sync,
                    text=text,
                    voice_id=voice_id or settings.lovo_voice_id_mm,
                ),
                timeout=tts_timeout_sec,
            )
        except Exception as exc:
            error_text = "timeout" if isinstance(exc, asyncio.TimeoutError) else str(exc)
            logger.info(
                "DUB3_TTS_FAIL",
                extra={
                    "task_id": task_id,
                    "step": "dub",
                    "stage": "DUB3_TTS_FAIL",
                    "dub_provider": provider,
                    "voice_id": voice_id,
                    "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
                    "error": error_text,
                },
            )
            raise DubbingError("LOVO timeout" if error_text == "timeout" else str(exc)) from exc
        suffix = ext or "wav"
        path = ws.write_mm_audio(content, suffix=suffix)
        logger.info(
            "DUB3_TTS_DONE",
            extra={
                "task_id": task_id,
                "step": "dub",
                "stage": "DUB3_TTS_DONE",
                "dub_provider": provider,
                "voice_id": voice_id,
                "elapsed_ms": int((time.perf_counter() - start_time) * 1000),
                "output_path": str(path),
                "output_size": path.stat().st_size if path.exists() else None,
            },
        )
        return {"audio_path": str(path), "duration_sec": None}

    raise DubbingError(f"Unsupported dub provider: {settings.dub_provider}")


async def synthesize_voice(*args: Any, **kwargs: Any) -> Any:
    """
    Legacy API surface preserved.
    Only supports text-based synthesis in the services layer.
    """
    try:
        if "mm_srt_text" not in kwargs:
            raise DubbingError(
                "mm_srt_text is required; use steps_v1.run_dub_step for DubRequest-based flow"
            )

        task_id = kwargs.get("task_id")
        if not task_id:
            raise DubbingError("task_id is required for dubbing synthesis")

        return await _synthesize_from_text(
            task_id=task_id,
            target_lang=kwargs.get("target_lang"),
            voice_id=kwargs.get("voice_id"),
            force=bool(kwargs.get("force", False)),
            mm_srt_text=kwargs.get("mm_srt_text") or "",
            workspace=kwargs.get("workspace"),
        )
    except Exception as e:
        # keep a stable error type for callers
        raise DubbingError(str(e)) from e


__all__ = ["DubbingError", "synthesize_voice"]
