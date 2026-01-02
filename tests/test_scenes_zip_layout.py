from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile


class FakeStorage:
    def __init__(self):
        self.keys = set()

    def upload_file(self, local_path: str, key: str, content_type: str | None = None) -> str:
        self.keys.add(key)
        return key

    def download_file(self, key: str, destination_path: str) -> None:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        return key in self.keys

    def generate_presigned_url(self, key: str, expiration: int = 3600) -> str:
        return f"https://example.invalid/{key}"


def test_scenes_zip_layout(tmp_path, monkeypatch) -> None:
    from gateway.app import config as app_config
    from gateway.app.ports.storage_provider import set_storage_service
    from gateway.app.services import scene_split
    from gateway.app.db import engine, ensure_task_extra_columns

    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    app_config.get_settings.cache_clear()
    ensure_task_extra_columns(engine)

    storage = FakeStorage()
    set_storage_service(storage)

    task_id = "scene_zip_001"
    raw = tmp_path / "tasks" / task_id / "raw" / "raw.mp4"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(b"raw")

    subs_dir = tmp_path / "deliver" / "subtitles" / task_id
    subs_dir.mkdir(parents=True, exist_ok=True)
    (subs_dir / "subtitles.json").write_text("{}", encoding="utf-8")
    subs_path = subs_dir / "mm.srt"
    subs_path.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nhello\n\n2\n00:00:02,500 --> 00:00:04,000\nworld\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        scene_split,
        "_slice_video",
        lambda _src, dst, _s, _e: dst.write_bytes(b"video"),
    )
    monkeypatch.setattr(
        scene_split,
        "_slice_audio",
        lambda _src, dst, _s, _e: dst.write_bytes(b"audio"),
    )

    result = scene_split.generate_scenes_package(task_id)
    zip_path = Path(result["zip_path"])
    assert zip_path.exists()

    prefix = f"deliver/scenes/{task_id}/"
    with ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        assert f"{prefix}README.md" in names
        assert f"{prefix}scenes_manifest.json" in names
        assert f"{prefix}scenes/scene_001/video.mp4" in names
        assert f"{prefix}scenes/scene_001/audio.wav" in names
        assert f"{prefix}scenes/scene_001/subs.srt" in names
        assert f"{prefix}scenes/scene_001/scene.json" in names

        readme = zf.read(f"{prefix}README.md").decode("utf-8")
        assert "Scenes.zip 使用说明" in readme

        manifest = json.loads(zf.read(f"{prefix}scenes_manifest.json").decode("utf-8"))
        assert manifest["task_id"] == task_id
        assert manifest["scenes"][0]["scene_id"] == "scene_001"
