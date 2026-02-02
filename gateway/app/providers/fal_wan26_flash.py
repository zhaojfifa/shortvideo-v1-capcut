from __future__ import annotations

import httpx
from typing import Optional

from gateway.app.ports.video_gen_provider import GeneratedVideo, VideoGenProvider

FAL_ENDPOINT = "https://fal.ai/models/wan/v2.6/image-to-video/flash"


class FalWan26FlashProvider(VideoGenProvider):
    def __init__(self, api_key: str):
        self.api_key = api_key

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
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{FAL_ENDPOINT}/api", json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()

        out_url = (
            data.get("video", {}).get("url")
            or data.get("output", {}).get("url")
            or data.get("url")
        )
        if not out_url:
            raise RuntimeError(f"FAL response missing video url: {data}")

        request_id = data.get("request_id") or data.get("id") or "fal-unknown"
        return GeneratedVideo(url=out_url, meta={"raw": data, "request_id": request_id})
