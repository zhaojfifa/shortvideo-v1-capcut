from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from gateway.app.core import workspace as workspace_module
from gateway.app.db import SessionLocal, ensure_task_extra_columns, engine
from gateway.app.schemas import ParseRequest
from gateway.app.services import steps_v1
from gateway.app.steps import parse as parse_module


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
                    "source_url": "https://www.tiktok.com/@demo/video/1",
                    "platform": "tiktok",
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


def test_run_parse_step_allows_tiktok_platform(monkeypatch, tmp_path: Path) -> None:
    task_id = "demo_parse_tiktok"
    _ensure_task(task_id)

    monkeypatch.setattr(workspace_module, "workspace_root", lambda: tmp_path)

    async def fake_parse_with_xiongmao(_url: str):
        return {
            "download_url": "https://example.com/raw.mp4",
            "title": "demo",
            "type": "VIDEO",
            "cover": None,
            "origin_text": "",
            "raw": None,
        }

    async def fake_download_raw_video(_task_id: str, _url: str) -> Path:
        raw = workspace_module.raw_path(task_id)
        raw.write_bytes(b"raw")
        return raw

    monkeypatch.setattr(parse_module, "parse_with_xiongmao", fake_parse_with_xiongmao)
    monkeypatch.setattr(parse_module, "download_raw_video", fake_download_raw_video)
    monkeypatch.setattr(steps_v1, "_upload_artifact", lambda *_args, **_kwargs: "raw/raw.mp4")

    result = asyncio.run(
        steps_v1.run_parse_step(
            ParseRequest(
                task_id=task_id,
                platform="tiktok",
                link="https://www.tiktok.com/@demo/video/1",
            )
        )
    )

    assert result["platform"] == "tiktok"

    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT platform FROM tasks WHERE id = :task_id"),
            {"task_id": task_id},
        ).fetchone()
        assert row and row[0] == "tiktok"
    finally:
        db.close()


def test_parse_video_detects_tiktok_from_url(monkeypatch, tmp_path: Path) -> None:
    task_id = "demo_parse_url"

    monkeypatch.setattr(workspace_module, "workspace_root", lambda: tmp_path)

    async def fake_parse_with_xiongmao(_url: str):
        return {
            "download_url": "https://example.com/raw.mp4",
            "title": "demo",
            "type": "VIDEO",
            "cover": None,
            "origin_text": "",
            "raw": None,
        }

    async def fake_download_raw_video(_task_id: str, _url: str) -> Path:
        raw = workspace_module.raw_path(task_id)
        raw.write_bytes(b"raw")
        return raw

    monkeypatch.setattr(parse_module, "parse_with_xiongmao", fake_parse_with_xiongmao)
    monkeypatch.setattr(parse_module, "download_raw_video", fake_download_raw_video)

    result = asyncio.run(
        parse_module.parse_video(
            task_id,
            "https://www.tiktok.com/@demo/video/2",
            platform_hint=None,
        )
    )

    assert result["platform"] == "tiktok"
