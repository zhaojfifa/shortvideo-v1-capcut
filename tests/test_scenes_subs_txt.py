from __future__ import annotations

from pathlib import Path


def test_scenes_have_subs_txt(monkeypatch, tmp_path: Path) -> None:
    from gateway.app.services import scene_split
    from gateway.app.core import workspace as workspace_module

    monkeypatch.setattr(workspace_module, "workspace_root", lambda: tmp_path)
    monkeypatch.setattr(scene_split, "workspace_root", lambda: tmp_path)

    raw = workspace_module.raw_path("demo_scene_txt")
    raw.write_bytes(b"fake")

    deliver_subs = tmp_path / "deliver" / "subtitles" / "demo_scene_txt"
    deliver_subs.mkdir(parents=True, exist_ok=True)
    (deliver_subs / "subtitles.json").write_text("{}", encoding="utf-8")
    srt_path = deliver_subs / "mm.srt"
    srt_path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nhello\n\n2\n00:00:01,000 --> 00:00:02,000\nworld\n",
        encoding="utf-8",
    )

    def fake_slice_video(_src, dst, _start, _end):
        Path(dst).write_bytes(b"video")

    def fake_slice_audio(_src, dst, _start, _end):
        Path(dst).write_bytes(b"audio")

    monkeypatch.setattr(scene_split, "_slice_video", fake_slice_video)
    monkeypatch.setattr(scene_split, "_slice_audio", fake_slice_audio)

    result = scene_split.generate_scenes_package("demo_scene_txt")
    assert result.get("scenes_key")

    package_root = tmp_path / "deliver" / "scenes" / "demo_scene_txt" / "scenes_package"
    scenes_root = package_root / "scenes"
    scenes = list(scenes_root.glob("scene_*"))
    assert scenes, "No scenes found"

    for scene_dir in scenes:
        srt = scene_dir / "subs.srt"
        txt = scene_dir / "subs.txt"
        if srt.exists():
            assert txt.exists(), f"Missing subs.txt for {scene_dir}"
            content = txt.read_text(encoding="utf-8")
            assert "-->" not in content
