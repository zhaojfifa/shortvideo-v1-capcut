from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
import wave
from typing import Optional

logger = logging.getLogger(__name__)

_model_lock = threading.Lock()
_model = None  # WhisperModel | None
_warmup_done = False


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_str(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    return value if value is not None and value != "" else default


def get_whisper_model():
    """
    Process-wide singleton for faster-whisper WhisperModel.
    Prevents per-request re-init (and the HF revision check HTTP call).
    """
    global _model
    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model

        try:
            from faster_whisper import WhisperModel
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("faster-whisper is not available") from exc

        model_size = _env_str("FASTER_WHISPER_MODEL") or _env_str("WHISPER_MODEL_SIZE", "small")
        device = _env_str("FASTWHISPER_DEVICE") or _env_str("WHISPER_DEVICE", "cpu")
        compute_type = _env_str("FASTWHISPER_COMPUTE_TYPE") or _env_str(
            "WHISPER_COMPUTE_TYPE",
            "int8",
        )
        download_root = _env_str("WHISPER_DOWNLOAD_ROOT")

        t0 = time.time()

        _model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=download_root,
        )
        dt_ms = int((time.time() - t0) * 1000)
        logger.info(
            "WHISPER_MODEL_INIT",
            extra={
                "model_size": model_size,
                "device": device,
                "compute_type": compute_type,
                "download_root": download_root,
                "init_ms": dt_ms,
            },
        )
        return _model


def transcribe(audio_path: str, **kwargs):
    model = get_whisper_model()
    vad_filter = _env_bool("FASTWHISPER_VAD_FILTER", default=False)
    language = _env_str("FASTWHISPER_LANGUAGE", default=None)
    if "vad_filter" not in kwargs:
        kwargs["vad_filter"] = vad_filter
    if language and "language" not in kwargs:
        kwargs["language"] = language
    return model.transcribe(audio_path, **kwargs)


def warmup() -> None:
    global _warmup_done
    if _warmup_done:
        return
    if not _env_bool("FASTWHISPER_WARMUP", default=False):
        return

    sec = _env_int("FASTWHISPER_WARMUP_SEC", 1)
    sec = max(1, min(sec, 3))

    t0 = time.time()
    fr = 16000
    nframes = fr * sec
    silence = (b"\x00\x00") * nframes

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as handle:
        with wave.open(handle.name, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(fr)
            wf.writeframes(silence)

        transcribe(handle.name, beam_size=1, best_of=1)

    dt_ms = int((time.time() - t0) * 1000)
    logger.info("WHISPER_WARMUP_DONE", extra={"warmup_ms": dt_ms, "sec": sec})
    _warmup_done = True
