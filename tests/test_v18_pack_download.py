from __future__ import annotations

import json
from zipfile import ZipFile


def test_download_pack_uses_pack_key(monkeypatch) -> None:
    from gateway.app.routers import tasks as tasks_module

    class Repo:
        def get(self, task_id: str):
            return {
                "task_id": task_id,
                "pack_type": "capcut_v18",
                "pack_key": "packs/demo/capcut_pack.zip",
                "pack_path": "legacy/path/ignored.zip",
            }

    calls = {}

    def fake_object_exists(key: str) -> bool:
        calls["key"] = key
        return True

    def fake_get_download_url(key: str) -> str:
        return f"url:{key}"

    monkeypatch.setattr(tasks_module, "object_exists", fake_object_exists)
    monkeypatch.setattr(tasks_module, "get_download_url", fake_get_download_url)

    resp = tasks_module.download_pack("demo_task", repo=Repo())
    assert resp.status_code == 302
    assert resp.headers["location"] == "url:packs/demo/capcut_pack.zip"
    assert calls["key"] == "packs/demo/capcut_pack.zip"


def test_create_capcut_pack_zip_structure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))

    from gateway.app import config as app_config
    from gateway.app.ports.storage_provider import set_storage_service

    app_config.get_settings.cache_clear()
    set_storage_service(app_config.create_storage_service())

    from gateway.app.core.workspace import pack_zip_path
    from gateway.app.services.pack_service import create_capcut_pack

    task_id = "task_v18_001"
    raw = tmp_path / "raw.mp4"
    audio = tmp_path / "voice_src.wav"
    subs = tmp_path / "subs.srt"

    raw.write_bytes(b"raw")
    audio.write_bytes(b"audio")
    subs.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")

    result = create_capcut_pack(
        task_id=task_id,
        raw_path=raw,
        audio_path=audio,
        subs_path=subs,
    )

    zip_path = pack_zip_path(task_id)
    assert zip_path.exists()

    prefix = f"deliver/packs/{task_id}/"
    expected = [
        f"{prefix}raw/raw.mp4",
        f"{prefix}audio/voice_my.wav",
        f"{prefix}subs/my.srt",
        f"{prefix}subs/mm.srt",
        f"{prefix}subs/mm.txt",
        f"{prefix}scenes/.keep",
        f"{prefix}manifest.json",
        f"{prefix}README.md",
    ]

    with ZipFile(zip_path) as zf:
        names = sorted(zf.namelist())
        assert sorted(expected) == names
        manifest = json.loads(zf.read(f"{prefix}manifest.json").decode("utf-8"))

    assert manifest == {
        "version": "1.8",
        "pack_type": "capcut_v18",
        "task_id": task_id,
        "language": "my",
        "assets": {
            "raw_video": "raw/raw.mp4",
            "voice": "audio/voice_my.wav",
            "subtitle": "subs/my.srt",
            "scenes_dir": "scenes/",
        },
    }
    assert result["files"] == expected
