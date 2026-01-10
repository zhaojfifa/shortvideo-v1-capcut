from __future__ import annotations

import time
from typing import Any


def log_step_timing(
    logger,
    *,
    task_id: str,
    step: str,
    start_time: float,
    provider: str | None = None,
    voice_id: str | None = None,
    edge_voice: str | None = None,
) -> None:
    duration_ms = int((time.perf_counter() - start_time) * 1000)
    payload: dict[str, Any] = {
        "task_id": task_id,
        "step": step,
        "duration_ms": duration_ms,
    }
    if provider:
        payload["provider"] = provider
    if voice_id:
        payload["voice_id"] = voice_id
    if edge_voice:
        payload["edge_voice"] = edge_voice
    logger.info("step_timing %s", payload)
