from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class FalWan26Request:
    image_url: str
    prompt: str
    duration_sec: int
    seed: Optional[int] = None


@dataclass
class FalWan26Result:
    video_url: str
    request_id: str


class FalWan26FlashProvider:
    """
    Provider wrapper: replaceable.
    PR-3 uses WAN v2.6 image-to-video FLASH.
    """

    def __init__(self, *, fal_key: str, model: str):
        self.fal_key = fal_key
        self.model = model

    async def generate(self, req: FalWan26Request) -> FalWan26Result:
        headers = {"Authorization": f"Key {self.fal_key}"}
        url = f"https://fal.run/{self.model}"
        payload = {
            "prompt": req.prompt,
            "image_url": req.image_url,
            "duration": req.duration_sec,
        }
        if req.seed is not None:
            payload["seed"] = int(req.seed)

        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        video_url = (
            data.get("video", {}).get("url")
            or data.get("output", {}).get("url")
            or data.get("url")
        )
        if not video_url:
            raise RuntimeError(f"FAL response missing video url: keys={list(data.keys())}")

        request_id = data.get("request_id") or data.get("id") or "fal-unknown"
        return FalWan26Result(video_url=video_url, request_id=request_id)
