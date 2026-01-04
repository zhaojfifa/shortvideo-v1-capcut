from __future__ import annotations

import asyncio
from pathlib import Path

from gateway.app import config
from gateway.app.core import workspace as workspace_module
from gateway.app.services import dubbing


def test_map_edge_voice_id_male() -> None:
    settings = config.get_settings()
    assert dubbing._map_edge_voice_id("mm_male_1", settings) == "my-MM-ThihaNeural"


def test_edge_tts_uses_male_voice(monkeypatch, tmp_path: Path) -> None:
    settings = config.get_settings()
    captured: dict[str, str] = {}

    async def fake_generate_audio_edge_tts(text: str, voice: str, output_path: str) -> None:
        captured["voice"] = voice
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"fake-audio")

    monkeypatch.setattr(dubbing, "generate_audio_edge_tts", fake_generate_audio_edge_tts)
    monkeypatch.setattr(workspace_module, "workspace_root", lambda: tmp_path)

    result = asyncio.run(
        dubbing._synthesize_from_text(
            task_id="demo_voice_male",
            target_lang="my",
            voice_id="mm_male_1",
            force=True,
            mm_srt_text="hello",
            workspace=None,
        )
    )

    assert captured["voice"] == "my-MM-ThihaNeural"
    assert result["audio_path"].endswith("_mm.mp3")
