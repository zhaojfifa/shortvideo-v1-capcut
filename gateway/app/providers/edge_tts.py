import logging
from pathlib import Path
from typing import Iterable

import edge_tts

from gateway.app.config import get_settings
from gateway.app.core.workspace import Workspace

logger = logging.getLogger(__name__)


class EdgeTTSError(RuntimeError):
    """Raised when Edge-TTS synthesis fails."""


class EdgeTTSProvider:
    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self.settings = get_settings()

    async def synthesize_mm(
        self,
        *,
        task_id: str,
        voice_id: str | None,
        lines: Iterable[str],
    ) -> Path:
        voice = self.settings.edge_tts_voice_map.get(voice_id or "mm_female_1")
        if not voice:
            raise EdgeTTSError(f"Unknown voice_id for Edge-TTS: {voice_id or 'mm_female_1'}")

        text = "\n".join(line.strip() for line in lines if line and line.strip()).strip()
        if not text:
            raise EdgeTTSError("No Burmese text provided for TTS")

        logger.info(
            "Calling Edge-TTS",
            extra={
                "task_id": task_id,
                "voice_id": voice_id,
                "voice": voice,
                "rate": self.settings.edge_tts_rate,
                "volume": self.settings.edge_tts_volume,
            },
        )

        communicate = edge_tts.Communicate(
            text=text,
            voice=voice,
            rate=self.settings.edge_tts_rate,
            volume=self.settings.edge_tts_volume,
        )
        audio_bytes = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes += chunk["data"]

        if not audio_bytes:
            raise EdgeTTSError("Edge-TTS returned no audio data")

        out_path = self.workspace.write_mm_audio(audio_bytes, suffix="mp3")
        return out_path
