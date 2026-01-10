from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient


def test_rerun_dub_forces_rerun_on_voice_change(monkeypatch) -> None:
    from gateway.app.main import app
    from gateway.app.routers import tasks as tasks_module
    from gateway.app.core.workspace import Workspace
    from gateway.app.ports.storage_provider import set_storage_service

    class Repo:
        def __init__(self) -> None:
            self.task = {
                "task_id": "demo",
                "voice_id": "mm_female_1",
                "mm_audio_key": "deliver/tasks/demo/audio_mm.mp3",
                "target_lang": "my",
            }

        def get(self, task_id: str):
            return self.task

        def upsert(self, task_id: str, payload: dict):
            self.task.update(payload)
            return payload

    class DummyStorage:
        def __init__(self) -> None:
            self.uploaded = None

        def upload_file(self, _local, key, content_type="application/octet-stream"):
            self.uploaded = (key, content_type)
            return key

    async def fake_run_dub_step(task) -> None:
        assert task.voice_id == "mm_male_1"
        assert task.force_dub is True
        ws = Workspace(task.task_id)
        ws.mm_audio_mp3_path.write_bytes(b"voice-test")

    monkeypatch.setattr(tasks_module, "run_dub_step_ssot", fake_run_dub_step)
    storage = DummyStorage()
    app.dependency_overrides[tasks_module.get_task_repository] = lambda: Repo()
    try:
        with TestClient(app) as client:
            set_storage_service(storage)
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
            assert data["mm_audio_key"] == "deliver/tasks/demo/audio_mm.mp3"
            assert storage.uploaded == ("deliver/tasks/demo/audio_mm.mp3", "audio/mpeg")
    finally:
        app.dependency_overrides.clear()


def test_rerun_dub_does_not_clear_audio_key_on_upload_failure(monkeypatch) -> None:
    from gateway.app.main import app
    from gateway.app.routers import tasks as tasks_module
    from gateway.app.core.workspace import Workspace
    from gateway.app.ports.storage_provider import set_storage_service

    class Repo:
        def __init__(self) -> None:
            self.task = {
                "task_id": "demo_fail",
                "voice_id": "mm_female_1",
                "mm_audio_key": "deliver/tasks/demo_fail/audio_mm.mp3",
                "target_lang": "my",
            }

        def get(self, task_id: str):
            return self.task

        def upsert(self, task_id: str, payload: dict):
            self.task.update(payload)
            return payload

    class FailingStorage:
        def upload_file(self, *_args, **_kwargs):
            raise RuntimeError("upload failed")
        
        def generate_presigned_url(self, *_args, **_kwargs):
            return "https://example.invalid/audio"

    async def fake_run_dub_step(task) -> None:
        ws = Workspace(task.task_id)
        ws.mm_audio_mp3_path.write_bytes(b"voice-test")

    repo = Repo()
    monkeypatch.setattr(tasks_module, "run_dub_step_ssot", fake_run_dub_step)
    app.dependency_overrides[tasks_module.get_task_repository] = lambda: repo
    try:
        with TestClient(app) as client:
            set_storage_service(FailingStorage())
            resp = client.post(
                "/api/tasks/demo_fail/dub",
                json={"provider": "edge_tts", "voice_id": "mm_male_1"},
            )
            assert resp.status_code == 500
            assert repo.task["mm_audio_key"] == "deliver/tasks/demo_fail/audio_mm.mp3"
    finally:
        app.dependency_overrides.clear()
        class ResetStorage:
            def upload_file(self, *_args, **_kwargs):
                return "deliver/tasks/demo_fail/audio_mm.mp3"

            def generate_presigned_url(self, *_args, **_kwargs):
                return "https://example.invalid/audio"

        set_storage_service(ResetStorage())
