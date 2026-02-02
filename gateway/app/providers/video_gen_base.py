from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class ProviderError(Exception):
    code: str
    message: str
    raw: Optional[object] = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class VideoGenProvider(Protocol):
    def generate_sync(
        self,
        *,
        image_url: str,
        prompt: str,
        duration_sec: int,
        resolution: str,
        request_id: str,
    ) -> str:
        """Return a downloadable video URL or raise ProviderError."""

