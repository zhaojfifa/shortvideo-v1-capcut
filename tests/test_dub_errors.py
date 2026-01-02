from __future__ import annotations

from fastapi.testclient import TestClient


def test_rerun_dub_returns_400_when_subtitles_missing(monkeypatch) -> None:
    from fastapi import HTTPException
    from gateway.app.main import app
    from gateway.app.routers import tasks as tasks_module

    class Repo:
        def get(self, task_id: str):
            return {"task_id": task_id}

        def upsert(self, task_id: str, payload: dict):
            return payload

    async def fake_run_dub_step(_task):
        raise HTTPException(status_code=400, detail="translated subtitles not found")

    monkeypatch.setattr(tasks_module, "run_dub_step_ssot", fake_run_dub_step)

    app.dependency_overrides[tasks_module.get_task_repository] = lambda: Repo()
    try:
        with TestClient(app) as client:
            resp = client.post("/api/tasks/demo/dub", json={})
            assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()
