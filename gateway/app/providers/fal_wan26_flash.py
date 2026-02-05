from __future__ import annotations

import httpx
from typing import Optional

from gateway.app.ports.video_gen_provider import GeneratedVideo, VideoGenProvider

FAL_ENDPOINT = "https://fal.ai/models"


class FalWan26FlashProvider(VideoGenProvider):
    def __init__(self, api_key: str, *, model: str, timeout_sec: int = 300, retries: int = 1):
        self.api_key = api_key
        self.model = model
        self.timeout_sec = timeout_sec
        self.retries = retries

    def _resolve_endpoint(self) -> str:
        if self.model.startswith("http://") or self.model.startswith("https://"):
            return self.model
        return f"{FAL_ENDPOINT}/{self.model}"

    async def generate_segment(
        self,
        avatar_image_url: str,
        ref_video_url: str,
        prompt: str,
        duration_sec: int,
        seed: Optional[int] = None,
    ) -> GeneratedVideo:
        if not self.api_key:
            raise RuntimeError("FAL_KEY missing")

        payload = {
            "prompt": prompt,
            "image_url": avatar_image_url,
            "video_url": ref_video_url,
            "duration": duration_sec,
        }
        if seed is not None:
            payload["seed"] = int(seed)

        headers = {"Authorization": f"Key {self.api_key}"}
        endpoint = self._resolve_endpoint()
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
                    r = await client.post(f"{endpoint}/api", json=payload, headers=headers)
                    r.raise_for_status()
                    data = r.json()
                last_err = None
                break
            except Exception as exc:
                last_err = exc
                if attempt >= self.retries:
                    raise
                continue
        if last_err is not None:
            raise last_err

        out_url = (
            data.get("video", {}).get("url")
            or data.get("output", {}).get("url")
            or data.get("url")
        )
        if not out_url:
            raise RuntimeError(f"FAL response missing video url: {data}")

        request_id = data.get("request_id") or data.get("id") or "fal-unknown"
        return GeneratedVideo(url=out_url, meta={"raw": data, "request_id": request_id})
