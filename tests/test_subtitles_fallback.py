from __future__ import annotations

import asyncio
from pathlib import Path


def test_subtitles_fallback_on_gemini_error(tmp_path, monkeypatch) -> None:
    from gateway.app import config as app_config
    from gateway.app.steps import subtitles as subtitles_module
    from gateway.app.core.workspace import Workspace
    from gateway.app.providers.gemini_subtitles import GeminiSubtitlesError

    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    app_config.get_settings.cache_clear()

    task_id = "subs_fallback_001"
    raw = tmp_path / "tasks" / task_id / "raw" / "raw.mp4"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(b"raw")

    def fake_extract(_video: Path, wav_path: Path) -> None:
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path.write_bytes(b"wav")

    def fake_transcribe(_audio: Path):
        return [
            {"index": 1, "start": 0.0, "end": 1.2, "origin": "hello"},
            {"index": 2, "start": 1.2, "end": 2.5, "origin": "world"},
        ]

    def fake_translate(*_args, **_kwargs):
        raise GeminiSubtitlesError("bad json")

    monkeypatch.setattr(subtitles_module, "_extract_audio", fake_extract)
    monkeypatch.setattr(subtitles_module, "_transcribe_with_faster_whisper", fake_transcribe)
    monkeypatch.setattr(subtitles_module, "translate_segments_with_gemini", fake_translate)

    result = asyncio.run(
        subtitles_module.generate_subtitles(task_id=task_id, target_lang="my")
    )

    workspace = Workspace(task_id)
    assert workspace.origin_srt_path.exists()
    assert workspace.mm_srt_path.exists()
    assert workspace.segments_json.exists()
    assert result["origin_srt"].strip() != ""
