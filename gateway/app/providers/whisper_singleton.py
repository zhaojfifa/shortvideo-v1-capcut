from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger(__name__)

_model_lock = threading.Lock()
_model = None  # WhisperModel | None


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

        model_size = os.getenv("WHISPER_MODEL_SIZE", "small")
        device = os.getenv("WHISPER_DEVICE", "cpu")
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
        download_root = os.getenv("WHISPER_DOWNLOAD_ROOT")

        logger.info(
            "WHISPER_MODEL_INIT",
            extra={
                "model_size": model_size,
                "device": device,
                "compute_type": compute_type,
                "download_root": download_root,
            },
        )

        _model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=download_root,
        )
        return _model
