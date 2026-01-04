from __future__ import annotations

import asyncio
from pathlib import Path


def test_dub_step_logs_timing(monkeypatch, tmp_path: Path) -> None:
    from gateway.app.services import steps_v1
    from gateway.app.core import workspace as workspace_module
    from gateway.app.schemas import DubRequest

    monkeypatch.setattr(workspace_module, "workspace_root", lambda: tmp_path)
    ws = workspace_module.Workspace("demo_timing")
    ws.write_mm_srt("1\n00:00:00,000 --> 00:00:01,000\nhello\n")
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")

    async def fake_synthesize_voice(**_kwargs):
        return {"audio_path": str(audio_path)}

    called = {"count": 0}

    def fake_log_step_timing(*_args, **_kwargs):
        called["count"] += 1

    monkeypatch.setattr(steps_v1, "synthesize_voice", fake_synthesize_voice)
    monkeypatch.setattr(steps_v1, "log_step_timing", fake_log_step_timing)
    monkeypatch.setattr(steps_v1, "get_storage_service", lambda: _DummyStorage())

    asyncio.run(steps_v1.run_dub_step(DubRequest(task_id="demo_timing", voice_id="mm_female_1")))

    assert called["count"] == 1


class _DummyStorage:
    def upload_file(self, _local, key, content_type="application/octet-stream"):
        return key
