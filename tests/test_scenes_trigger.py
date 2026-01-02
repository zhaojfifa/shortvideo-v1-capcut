from __future__ import annotations

from fastapi import BackgroundTasks


def test_trigger_scenes_idempotent(monkeypatch) -> None:
    from gateway.app.routers import tasks as tasks_module

    class Repo:
        def __init__(self) -> None:
            self.data = {
                "task_id": "scene_ready_001",
                "scenes_key": "deliver/scenes/scene_ready_001/scenes.zip",
            }

        def get(self, task_id: str):
            return self.data if task_id == "scene_ready_001" else None

        def upsert(self, task_id: str, payload: dict):
            self.data.update(payload)
            return self.data

    monkeypatch.setattr(tasks_module, "object_exists", lambda _k: True)

    resp = tasks_module.build_scenes(
        "scene_ready_001",
        background_tasks=BackgroundTasks(),
        payload=None,
        repo=Repo(),
    )
    assert resp["status"] == "already_ready"


def test_trigger_scenes_sets_status(monkeypatch) -> None:
    from gateway.app.routers import tasks as tasks_module

    class Repo:
        def __init__(self) -> None:
            self.data = {"task_id": "scene_new_001", "scenes_key": None}

        def get(self, task_id: str):
            return self.data if task_id == "scene_new_001" else None

        def upsert(self, task_id: str, payload: dict):
            self.data.update(payload)
            return self.data

    monkeypatch.setattr(tasks_module, "object_exists", lambda _k: False)

    resp = tasks_module.build_scenes(
        "scene_new_001",
        background_tasks=BackgroundTasks(),
        payload=None,
        repo=Repo(),
    )
    assert resp["status"] == "queued"
