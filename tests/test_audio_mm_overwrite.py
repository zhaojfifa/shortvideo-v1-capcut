from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient
from datetime import datetime, timezone
from sqlalchemy import text

from gateway.app.core import workspace as workspace_module
from gateway.app.db import SessionLocal, ensure_task_extra_columns, engine
from gateway.app.schemas import DubRequest, PackRequest
from gateway.app.services import steps_v1


def _ensure_task(task_id: str) -> None:
    ensure_task_extra_columns(engine)
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT id FROM tasks WHERE id = :task_id"),
            {"task_id": task_id},
        ).fetchone()
        if not row:
            db.execute(
                text(
                    "INSERT INTO tasks "
                    "(id, tenant_id, project_id, source_url, platform, category_key, content_lang, "
                    "target_lang, ui_lang, face_swap_enabled, status, created_at, updated_at) "
                    "VALUES (:id, :tenant_id, :project_id, :source_url, :platform, :category_key, "
                    ":content_lang, :target_lang, :ui_lang, :face_swap_enabled, :status, :created_at, :updated_at)"
                ),
                {
                    "id": task_id,
                    "tenant_id": "default",
                    "project_id": "default",
                    "source_url": "https://example.com",
                    "platform": "douyin",
                    "category_key": "beauty",
                    "content_lang": "my",
                    "target_lang": "my",
                    "ui_lang": "en",
                    "face_swap_enabled": 0,
                    "status": "pending",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            db.commit()
    finally:
        db.close()


def test_run_dub_step_uploads_audio_mm_key(monkeypatch, tmp_path: Path) -> None:
    task_id = "demo_audio_key"
    _ensure_task(task_id)

    monkeypatch.setattr(workspace_module, "workspace_root", lambda: tmp_path)
    ws = workspace_module.Workspace(task_id)
    ws.write_mm_srt("1\n00:00:00,000 --> 00:00:01,000\nhello\n")

    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")

    async def fake_synthesize_voice(**_kwargs):
        return {"audio_path": str(audio_path)}

    class DummyStorage:
        def __init__(self):
            self.uploaded_key = None

        def upload_file(self, _local, key, content_type=None):
            self.uploaded_key = key
            return key

    dummy = DummyStorage()
    monkeypatch.setattr(steps_v1, "synthesize_voice", fake_synthesize_voice)
    monkeypatch.setattr(steps_v1, "get_storage_service", lambda: dummy)

    asyncio.run(
        steps_v1.run_dub_step(
            DubRequest(task_id=task_id, target_lang="my", voice_id="mm_male_1")
        )
    )

    assert dummy.uploaded_key == f"deliver/tasks/{task_id}/audio_mm.mp3"

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT mm_audio_key FROM tasks WHERE id = :task_id"),
            {"task_id": task_id},
        ).fetchone()
        assert row and row[0] == dummy.uploaded_key
    finally:
        db.close()


def test_run_dub_step_uses_mm_text_override(monkeypatch, tmp_path: Path) -> None:
    task_id = "demo_dub_override"
    _ensure_task(task_id)

    monkeypatch.setattr(workspace_module, "workspace_root", lambda: tmp_path)
    ws = workspace_module.Workspace(task_id)
    ws.write_mm_srt("1\n00:00:00,000 --> 00:00:01,000\noriginal\n")

    audio_path = tmp_path / "audio_override.mp3"
    audio_path.write_bytes(b"audio")

    captured = {}

    async def fake_synthesize_voice(**kwargs):
        captured["mm_srt_text"] = kwargs.get("mm_srt_text")
        return {"audio_path": str(audio_path)}

    class DummyStorage:
        def __init__(self):
            self.uploaded_key = None

        def upload_file(self, _local, key, content_type=None):
            self.uploaded_key = key
            return key

    dummy = DummyStorage()
    monkeypatch.setattr(steps_v1, "synthesize_voice", fake_synthesize_voice)
    monkeypatch.setattr(steps_v1, "get_storage_service", lambda: dummy)

    asyncio.run(
        steps_v1.run_dub_step(
            DubRequest(
                task_id=task_id,
                target_lang="my",
                voice_id="mm_male_1",
                mm_text="override text",
            )
        )
    )

    assert captured["mm_srt_text"] == "override text"


def test_audio_mm_download_uses_mm_audio_key(monkeypatch) -> None:
    from gateway.app.main import app
    from gateway.app.deps import get_task_repository
    from gateway.app.routers import tasks as tasks_module

    class DummyRepo:
        def get(self, _task_id):
            return {"mm_audio_key": "deliver/tasks/demo/audio_mm.mp3"}

    app.dependency_overrides[get_task_repository] = lambda: DummyRepo()
    monkeypatch.setattr(
        tasks_module,
        "get_download_url",
        lambda key, **_kw: f"https://example.invalid/{key}",
    )
    try:
        with TestClient(app, follow_redirects=False) as client:
            resp = client.get("/v1/tasks/demo/audio_mm")
            assert resp.status_code == 302
            assert resp.headers["location"] == "https://example.invalid/deliver/tasks/demo/audio_mm.mp3"
    finally:
        app.dependency_overrides.clear()


def test_pack_step_downloads_mm_audio_key(monkeypatch, tmp_path: Path) -> None:
    task_id = "demo_pack_audio"
    _ensure_task(task_id)

    monkeypatch.setattr(workspace_module, "workspace_root", lambda: tmp_path)
    ws = workspace_module.Workspace(task_id)
    raw_path = workspace_module.raw_path(task_id)
    raw_path.write_bytes(b"raw")
    ws.write_mm_srt("1\n00:00:00,000 --> 00:00:01,000\nhello\n")

    db = SessionLocal()
    try:
        db.execute(
            text("UPDATE tasks SET mm_audio_key = :key WHERE id = :task_id"),
            {"key": f"deliver/tasks/{task_id}/audio_mm.mp3", "task_id": task_id},
        )
        db.commit()
    finally:
        db.close()

    class DummyStorage:
        def __init__(self):
            self.download_key = None

        def download_file(self, key, local_path):
            self.download_key = key
            Path(local_path).write_bytes(b"audio")

        def upload_file(self, *_args, **_kwargs):
            return "packs/demo/capcut_pack.zip"

        def generate_presigned_url(self, *_args, **_kwargs):
            return "https://example.invalid/pack.zip"

    dummy = DummyStorage()
    monkeypatch.setattr(steps_v1, "get_storage_service", lambda: dummy)

    asyncio.run(steps_v1.run_pack_step(PackRequest(task_id=task_id)))

    assert dummy.download_key == f"deliver/tasks/{task_id}/audio_mm.mp3"
