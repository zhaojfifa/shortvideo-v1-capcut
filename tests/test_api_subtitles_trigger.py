from __future__ import annotations

from pathlib import Path


def test_api_subtitles_idempotent(monkeypatch) -> None:
    from gateway.app.routers import tasks as tasks_module

    class Repo:
        def __init__(self) -> None:
            self.data = {
                "task_id": "subs_ready_001",
                "subtitles_status": "ready",
                "subtitles_key": "deliver/subtitles/subs_ready_001/subtitles.json",
            }

        def get(self, task_id: str):
            return self.data if task_id == "subs_ready_001" else None

        def upsert(self, task_id: str, payload: dict):
            self.data.update(payload)
            return self.data

    resp = tasks_module.build_subtitles("subs_ready_001", payload=None, repo=Repo())
    assert resp["status"] == "already_ready"


def test_api_subtitles_runs(monkeypatch, tmp_path) -> None:
    from gateway.app import config as app_config
    from gateway.app.routers import tasks as tasks_module
    from gateway.app.core.workspace import Workspace
    from gateway.app.ports.storage_provider import set_storage_service

    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    app_config.get_settings.cache_clear()

    class FakeStorage:
        def upload_file(self, local_path: str, key: str, content_type: str | None = None) -> str:
            return key

        def download_file(self, key: str, destination_path: str) -> None:
            raise NotImplementedError

        def exists(self, key: str) -> bool:
            return True

        def generate_presigned_url(self, key: str, expiration: int = 3600) -> str:
            return f"https://example.invalid/{key}"

    set_storage_service(FakeStorage())

    async def fake_run_subtitles(req):
        ws = Workspace(req.task_id)
        ws.origin_srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
        ws.mm_srt_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nmm\n", encoding="utf-8")
        ws.segments_json.write_text("{}", encoding="utf-8")
        return {"ok": True}

    monkeypatch.setattr(tasks_module, "run_subtitles_step_v1", fake_run_subtitles)

    class Repo:
        def __init__(self) -> None:
            self.data = {"task_id": "subs_run_001", "content_lang": "my"}

        def get(self, task_id: str):
            return self.data if task_id == "subs_run_001" else None

        def upsert(self, task_id: str, payload: dict):
            self.data.update(payload)
            return self.data

    resp = tasks_module.build_subtitles("subs_run_001", payload=None, repo=Repo())
    assert resp.task_id == "subs_run_001"
    assert resp.subtitles_status == "ready"
