from __future__ import annotations

from pathlib import Path


def test_scenes_uses_deliver_subtitles(tmp_path, monkeypatch) -> None:
    from gateway.app import config as app_config
    from gateway.app.services import scene_split
    from gateway.app.ports.storage_provider import set_storage_service

    class FakeStorage:
        def upload_file(self, local_path: str, key: str, content_type: str | None = None) -> str:
            return key

        def download_file(self, key: str, destination_path: str) -> None:
            raise NotImplementedError

        def exists(self, key: str) -> bool:
            return True

        def generate_presigned_url(self, key: str, expiration: int = 3600) -> str:
            return f"https://example.invalid/{key}"

    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    app_config.get_settings.cache_clear()
    set_storage_service(FakeStorage())

    task_id = "scene_subs_001"
    raw = tmp_path / "tasks" / task_id / "raw" / "raw.mp4"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(b"raw")

    subs_dir = tmp_path / "deliver" / "subtitles" / task_id
    subs_dir.mkdir(parents=True, exist_ok=True)
    (subs_dir / "subtitles.json").write_text("{}", encoding="utf-8")
    (subs_dir / "origin.srt").write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nhello\n",
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
    assert Path(result["zip_path"]).exists()
