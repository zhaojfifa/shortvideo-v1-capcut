from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_scenes_redirect_302(monkeypatch) -> None:
    from gateway.app.main import app
    from gateway.routes import v1 as v1_module
    from gateway.app.db import SessionLocal
    from gateway.app import models

    monkeypatch.setattr(v1_module, "object_exists", lambda _k: True)
    monkeypatch.setattr(v1_module, "get_download_url", lambda key, **_kw: f"https://example.invalid/{key}")
    try:
        db = SessionLocal()
        task = db.query(models.Task).filter(models.Task.id == "demo").first()
        if not task:
            task = models.Task(
                id="demo",
                source_url="https://example.com",
                platform="douyin",
                category_key="beauty",
                content_lang="my",
                ui_lang="en",
                status="pending",
            )
            db.add(task)
        task.scenes_key = "deliver/scenes/demo/scenes.zip"
        db.commit()
        db.close()
        with TestClient(app, follow_redirects=False) as client:
            resp = client.get("/v1/tasks/demo/scenes")
            assert resp.status_code == 302
            assert resp.headers["location"] == "https://example.invalid/deliver/scenes/demo/scenes.zip"
    finally:
        app.dependency_overrides.clear()


def test_get_scenes_404_when_missing(monkeypatch) -> None:
    from gateway.app.main import app
    from gateway.routes import v1 as v1_module
    from gateway.app.db import SessionLocal
    from gateway.app import models

    monkeypatch.setattr(v1_module, "object_exists", lambda _k: False)
    try:
        db = SessionLocal()
        task = db.query(models.Task).filter(models.Task.id == "demo").first()
        if not task:
            task = models.Task(
                id="demo",
                source_url="https://example.com",
                platform="douyin",
                category_key="beauty",
                content_lang="my",
                ui_lang="en",
                status="pending",
            )
            db.add(task)
        task.scenes_key = None
        db.commit()
        db.close()
        with TestClient(app, follow_redirects=False) as client:
            resp = client.get("/v1/tasks/demo/scenes")
            assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
