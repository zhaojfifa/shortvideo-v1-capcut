from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient


def test_rerun_dub_forces_rerun_on_voice_change(monkeypatch) -> None:
    from gateway.app.main import app
    from gateway.app.routers import tasks as tasks_module
    from gateway.app.core.workspace import Workspace

    class Repo:
        def __init__(self) -> None:
            self.task = {
                "task_id": "demo",
                "voice_id": "mm_female_1",
                "mm_audio_path": "deliver/packs/demo/audio_mm.mp3",
                "target_lang": "my",
            }

        def get(self, task_id: str):
            return self.task

        def upsert(self, task_id: str, payload: dict):
            self.task.update(payload)
            return payload

    async def fake_run_dub_step(task) -> None:
        assert task.voice_id == "mm_male_1"
        assert task.force_dub is True
        ws = Workspace(task.task_id)
        ws.mm_audio_mp3_path.write_bytes(b"voice-test")

    monkeypatch.setattr(tasks_module, "run_dub_step_ssot", fake_run_dub_step)
    app.dependency_overrides[tasks_module.get_task_repository] = lambda: Repo()
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/tasks/demo/dub",
                json={"provider": "edge_tts", "voice_id": "mm_male_1"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["resolved_voice_id"] == "mm_male_1"
            assert data["resolved_edge_voice"] == "my-MM-ThihaNeural"
            expected_hash = hashlib.sha256(b"voice-test").hexdigest()
            assert data["audio_sha256"] == expected_hash
            assert data["mm_audio_key"]
    finally:
        app.dependency_overrides.clear()
