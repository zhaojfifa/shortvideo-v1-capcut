from __future__ import annotations

from fastapi.testclient import TestClient


def test_v1_subtitles_alias_exists(monkeypatch) -> None:
    from gateway import routes
    from gateway.main import app

    async def fake_run(req):
        return {"task_id": req.task_id, "ok": True}

    monkeypatch.setattr(routes.v1, "run_subtitles_step", fake_run)

    with TestClient(app) as client:
        resp = client.post("/v1/subtitles", json={"task_id": "demo"})
        assert resp.status_code == 200
