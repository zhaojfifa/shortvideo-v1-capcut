"""
Compatibility shim for legacy imports: gateway.app.services.dubbing

IMPORTANT:
- Do NOT implement dubbing logic here.
- Route to v1.62+ step/usecase that reads subtitles.json (SSOT).
"""

from __future__ import annotations

import importlib
import logging
import re
from typing import Any, Callable, Optional

from gateway.app.config import get_settings
from gateway.app.core.workspace import Workspace
from gateway.app.providers.edge_tts import EdgeTTSError, generate_audio_edge_tts
from gateway.app.providers import lovo_tts
from gateway.app.schemas import DubRequest

logger = logging.getLogger(__name__)


class DubbingError(RuntimeError):
    """Raised when dubbing synthesis fails."""


def _resolve_callable() -> Callable[..., Any]:
    """
    Try to find the real dubbing entrypoint in the refactored codebase.
    We intentionally support multiple candidates to avoid tight coupling.
    """
    candidates = [
        # Prefer v1 steps (DubRequest-based)
        ("gateway.app.services.steps_v1", "run_dub_step"),

        # Most likely: steps layer
        ("gateway.app.steps.dub", "synthesize_voice"),
        ("gateway.app.steps.dubbing", "synthesize_voice"),

        # Alternative: usecase/application layer naming
        ("gateway.app.usecases.dub", "run_dub_step"),
        ("gateway.app.usecases.dubbing", "run_dub_step"),
        ("gateway.app.usecases.dub", "synthesize_voice"),
        ("gateway.app.usecases.dubbing", "synthesize_voice"),

        # Sometimes people put it under services/steps_v1 during migration
        ("gateway.app.steps_v1.dub", "run_dub_step"),
        ("gateway.app.steps_v1.dubbing", "run_dub_step"),
    ]

    last_err: Optional[Exception] = None
    for mod_name, attr in candidates:
        try:
            mod = importlib.import_module(mod_name)
            fn = getattr(mod, attr, None)
            if callable(fn):
                return fn  # type: ignore[return-value]
        except Exception as e:
            last_err = e

    raise ImportError(
        "Cannot resolve dubbing entrypoint. "
        "Expected run_dub_step/synthesize_voice in one of: "
        + ", ".join([f"{m}.{a}" for m, a in candidates])
        + (f". Last error: {last_err}" if last_err else "")
    )


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

    text = _normalize_text(mm_srt_text)
    if not text:
        raise DubbingError("Empty text for dubbing")

    settings = get_settings()
    provider = (settings.dub_provider or "edge-tts").lower()
    if provider == "edge":
        provider = "edge-tts"

    if provider == "edge-tts":
        voice_key = voice_id or "mm_female_1"
        voice = settings.edge_tts_voice_map.get(voice_key, voice_key)
        output_path = ws.mm_audio_mp3_path
        try:
            await generate_audio_edge_tts(text, voice, str(output_path))
        except EdgeTTSError as exc:
            raise DubbingError(str(exc)) from exc
        except Exception as exc:
            raise DubbingError(f"Edge-TTS failed: {exc}") from exc
        if not output_path.exists():
            raise DubbingError("Edge-TTS did not produce audio output")
        return {"audio_path": str(output_path), "duration_sec": None}

    if provider == "lovo":
        try:
            content, ext, _ = lovo_tts.synthesize_sync(
                text=text,
                voice_id=voice_id or settings.lovo_voice_id_mm,
            )
        except Exception as exc:
            raise DubbingError(str(exc)) from exc
        suffix = ext or "wav"
        path = ws.write_mm_audio(content, suffix=suffix)
        return {"audio_path": str(path), "duration_sec": None}

    raise DubbingError(f"Unsupported dub provider: {settings.dub_provider}")


async def synthesize_voice(*args: Any, **kwargs: Any) -> Any:
    """
    Legacy API surface preserved.
    Routes DubRequest-based calls to steps_v1, otherwise falls back to text synthesis.
    """
    try:
        from gateway.app.services.steps_v1 import (
            run_dub_step as run_dub_step_v1,
        )  # lazy import to avoid circular import
        if args and isinstance(args[0], DubRequest):
            return await run_dub_step_v1(args[0])

        task_id = kwargs.get("task_id")
        if task_id and "mm_srt_text" not in kwargs:
            req = DubRequest(
                task_id=task_id,
                voice_id=kwargs.get("voice_id"),
                target_lang=kwargs.get("target_lang") or "my",
                force=bool(kwargs.get("force", False)),
            )
            return await run_dub_step_v1(req)

        if "mm_srt_text" in kwargs:
            return await _synthesize_from_text(
                task_id=task_id,
                target_lang=kwargs.get("target_lang"),
                voice_id=kwargs.get("voice_id"),
                force=bool(kwargs.get("force", False)),
                mm_srt_text=kwargs.get("mm_srt_text") or "",
                workspace=kwargs.get("workspace"),
            )

        fn = _resolve_callable()
        result = fn(*args, **kwargs)
        if hasattr(result, "__await__"):
            return await result
        return result
    except Exception as e:
        # keep a stable error type for callers
        raise DubbingError(str(e)) from e


__all__ = ["DubbingError", "synthesize_voice"]
