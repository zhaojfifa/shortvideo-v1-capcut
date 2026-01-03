from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_scenes_redirect_302(monkeypatch) -> None:
    from gateway.app.main import app
    from gateway.app.deps import get_task_repository
    from gateway.app.routers import tasks as tasks_module

    monkeypatch.setattr(tasks_module, "object_exists", lambda _k: True)
    monkeypatch.setattr(
        tasks_module,
        "get_download_url",
        lambda key, **_kw: f"https://example.invalid/{key}",
    )
    try:
        class DummyRepo:
            def get(self, _task_id):
                return {"scenes_key": "deliver/scenes/demo/scenes.zip"}

        app.dependency_overrides[get_task_repository] = lambda: DummyRepo()
        with TestClient(app, follow_redirects=False) as client:
            resp = client.get("/v1/tasks/demo/scenes")
            assert resp.status_code == 302
            assert resp.headers["location"] == "https://example.invalid/deliver/scenes/demo/scenes.zip"
    finally:
        app.dependency_overrides.clear()


def test_get_scenes_404_when_missing(monkeypatch) -> None:
    from gateway.app.main import app
    from gateway.app.deps import get_task_repository
    from gateway.app.routers import tasks as tasks_module

    monkeypatch.setattr(tasks_module, "object_exists", lambda _k: False)
    try:
        class DummyRepo:
            def get(self, _task_id):
                return {"scenes_key": None}

        app.dependency_overrides[get_task_repository] = lambda: DummyRepo()
        with TestClient(app, follow_redirects=False) as client:
            resp = client.get("/v1/tasks/demo/scenes")
            assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
