from __future__ import annotations

from pathlib import Path


def test_scene_slice_video_is_muted(monkeypatch, tmp_path: Path) -> None:
    from gateway.app.services import scene_split

    src = tmp_path / "src.mp4"
    dst = tmp_path / "out.mp4"
    src.write_bytes(b"fake")

    captured = {"args": None}

    def fake_ffmpeg_path() -> str:
        return "ffmpeg"

    def fake_run_ffmpeg(args: list[str]) -> None:
        captured["args"] = args
        Path(args[-1]).write_bytes(b"out")

    monkeypatch.setattr(scene_split, "_ffmpeg_path", fake_ffmpeg_path)
    monkeypatch.setattr(scene_split, "_run_ffmpeg", fake_run_ffmpeg)

    scene_split._slice_video(src, dst, 0.0, 1.0)

    assert captured["args"] is not None
    assert "-an" in captured["args"]
