from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from gateway.app.core import workspace as workspace_module
from gateway.app.main import app
from gateway.app.deps import get_task_repository
from gateway.app.routers import tasks as tasks_module


def test_save_mm_edited_overwrites_mm_txt(monkeypatch, tmp_path: Path) -> None:
    task_id = "demo_mm_edited_save"
    monkeypatch.setattr(workspace_module, "workspace_root", lambda: tmp_path)

    captured = {}

    def fake_upload_task_artifact(_task, _local_path, artifact_name, task_id=None, **_kwargs):
        captured["artifact_name"] = artifact_name
        return f"deliver/tasks/{task_id}/{artifact_name}"

    class DummyRepo:
        def __init__(self):
            self.task = {"task_id": task_id, "mm_srt_path": "subs/mm.srt"}

        def get(self, _task_id):
            return self.task

        def upsert(self, _task_id, fields):
            self.task.update(fields)

    app.dependency_overrides[get_task_repository] = lambda: DummyRepo()
    monkeypatch.setattr(tasks_module, "upload_task_artifact", fake_upload_task_artifact)

    try:
        with TestClient(app) as client:
            resp = client.post(
                f"/api/tasks/{task_id}/mm_edited",
                json={"text": "edited text"},
            )
            assert resp.status_code == 200

        ws = workspace_module.Workspace(task_id)
        assert ws.mm_txt_path.read_text(encoding="utf-8") == "edited text\n"
        assert captured["artifact_name"] == "subs/mm.txt"
    finally:
        app.dependency_overrides.clear()
