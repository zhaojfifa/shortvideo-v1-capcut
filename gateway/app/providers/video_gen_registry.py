from __future__ import annotations

from gateway.app.config import (
    APOLLO_AVATAR_PROVIDER,
    APOLLO_AVATAR_LIVE_MODEL,
    APOLLO_AVATAR_LIVE_TIMEOUT_SEC,
    FAL_KEY,
)
from gateway.app.ports.video_gen_provider import VideoGenProvider
from gateway.app.providers.fal_wan26_flash import FalWan26FlashProvider


def get_video_gen_provider() -> VideoGenProvider:
    name = (APOLLO_AVATAR_PROVIDER or "fal_wan26_flash").strip()
    if name == "fal_wan26_flash":
        return FalWan26FlashProvider(
            api_key=FAL_KEY,
            model=APOLLO_AVATAR_LIVE_MODEL or "wan/v2.6/image-to-video/flash",
            timeout_sec=APOLLO_AVATAR_LIVE_TIMEOUT_SEC or 300,
        )
    raise ValueError(f"Unknown APOLLO_AVATAR_PROVIDER: {name}")
