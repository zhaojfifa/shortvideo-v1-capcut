from __future__ import annotations

from gateway.app.config import APOLLO_AVATAR_PROVIDER, FAL_KEY
from gateway.app.ports.video_gen_provider import VideoGenProvider
from gateway.app.providers.fal_wan26_flash import FalWan26FlashProvider


def get_video_gen_provider() -> VideoGenProvider:
    name = (APOLLO_AVATAR_PROVIDER or "fal_wan26_flash").strip()
    if name == "fal_wan26_flash":
        return FalWan26FlashProvider(api_key=FAL_KEY)
    raise ValueError(f"Unknown APOLLO_AVATAR_PROVIDER: {name}")
