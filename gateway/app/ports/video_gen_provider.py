from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


@dataclass
class GeneratedVideo:
    url: str
    meta: Dict[str, Any]


class VideoGenProvider(Protocol):
    async def generate_segment(
        self,
        avatar_image_url: str,
        ref_video_url: str,
        prompt: str,
        duration_sec: int,
        seed: Optional[int] = None,
    ) -> GeneratedVideo:
        ...
