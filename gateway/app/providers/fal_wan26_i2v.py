from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from gateway.app import config
from gateway.app.providers.video_gen_base import ProviderError, VideoGenProvider

log = logging.getLogger(__name__)


class FalWan26I2VProvider(VideoGenProvider):
    """
    fal.ai provider wrapper for Wan 2.6 Image-to-Video.
    Model id is configured via env: FAL_WAN26_MODEL_ID (default flash).
    """

    def __init__(
        self,
        *,
        fal_key: str,
        model_id: str,
        timeout_sec: int,
        poll_interval_sec: float,
        poll_max_interval_sec: float,
    ) -> None:
        self.fal_key = fal_key
        self.model_id = model_id
        self.timeout_sec = timeout_sec
        self.poll_interval_sec = poll_interval_sec
        self.poll_max_interval_sec = poll_max_interval_sec
        if not self.fal_key:
            raise ProviderError("fal_key_missing", "FAL_KEY is required for live runs")

    def generate_sync(
        self,
        *,
        image_url: str,
        prompt: str,
        duration_sec: int,
        resolution: str,
        request_id: str,
    ) -> str:
        try:
            import fal_client  # type: ignore
        except Exception as exc:
            raise ProviderError(
                "fal_client_import_failed",
                "fal_client import failed",
                raw=str(exc),
            ) from exc

        payload: Dict[str, Any] = {
            "image_url": image_url,
            "prompt": prompt,
            "duration": duration_sec,
            "resolution": resolution,
        }

        start = time.time()
        log.info(
            "[ApolloAvatar] fal submit start request_id=%s model_id=%s",
            request_id,
            self.model_id,
        )
        try:
            handler = fal_client.submit(
                self.model_id,
                arguments=payload,
                key=self.fal_key,
            )
        except Exception as exc:
            raise ProviderError("fal_submit_failed", "fal submit failed", raw=str(exc)) from exc

        interval = max(self.poll_interval_sec, 0.5)
        deadline = start + float(self.timeout_sec)
        while True:
            if time.time() >= deadline:
                raise ProviderError("fal_timeout", f"fal job timeout after {self.timeout_sec}s")
            try:
                status = fal_client.status(handler, key=self.fal_key)
            except Exception as exc:
                raise ProviderError("fal_status_failed", "fal status failed", raw=str(exc)) from exc

            state = getattr(status, "status", None) or getattr(status, "state", None) or str(status)
            state_l = str(state).lower()
            if "completed" in state_l or "succeeded" in state_l or state_l == "done":
                break
            if "failed" in state_l or "error" in state_l:
                raw = getattr(status, "error", None) or getattr(status, "detail", None) or str(status)
                raise ProviderError("fal_job_failed", "fal job failed", raw=raw)

            time.sleep(interval)
            interval = min(interval * 1.4, self.poll_max_interval_sec)

        try:
            result = fal_client.result(handler, key=self.fal_key)
        except Exception as exc:
            raise ProviderError("fal_result_failed", "fal result failed", raw=str(exc)) from exc

        video_url = _extract_video_url(result)
        if not video_url:
            raise ProviderError("fal_no_video_url", "fal result missing video url", raw=result)

        elapsed = int((time.time() - start) * 1000)
        log.info("[ApolloAvatar] fal submit done request_id=%s elapsed_ms=%s", request_id, elapsed)
        return video_url


def _extract_video_url(result: Any) -> Optional[str]:
    if isinstance(result, dict):
        for key in ("video_url", "url"):
            value = result.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
        outputs = result.get("outputs") or result.get("output") or result.get("videos")
        if isinstance(outputs, list) and outputs:
            first = outputs[0]
            if isinstance(first, dict):
                url = first.get("url") or first.get("video_url")
                if isinstance(url, str) and url.startswith("http"):
                    return url
    for attr in ("video_url", "url"):
        value = getattr(result, attr, None)
        if isinstance(value, str) and value.startswith("http"):
            return value
    outputs = getattr(result, "outputs", None) or getattr(result, "videos", None)
    if isinstance(outputs, list) and outputs:
        first = outputs[0]
        if isinstance(first, dict):
            url = first.get("url") or first.get("video_url")
            if isinstance(url, str) and url.startswith("http"):
                return url
        url = getattr(first, "url", None) or getattr(first, "video_url", None)
        if isinstance(url, str) and url.startswith("http"):
            return url
    return None


def build_default_provider() -> FalWan26I2VProvider:
    return FalWan26I2VProvider(
        fal_key=config.FAL_KEY,
        model_id=config.FAL_WAN26_MODEL_ID,
        timeout_sec=config.WAN26_TIMEOUT_SEC,
        poll_interval_sec=config.WAN26_POLL_INTERVAL_SEC,
        poll_max_interval_sec=config.WAN26_POLL_MAX_INTERVAL_SEC,
    )

