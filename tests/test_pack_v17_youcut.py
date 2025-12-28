from __future__ import annotations

import json
from pathlib import Path

from gateway.app.core.pack_v17_youcut import generate_youcut_pack


def test_generate_youcut_pack_structure(tmp_path: Path) -> None:
    task_id = "demo_task_001"
    pack_root = generate_youcut_pack(task_id, tmp_path, placeholders=True)

    assert pack_root.exists()
    assert (pack_root / "raw" / "raw.mp4").exists()
    assert (pack_root / "audio" / "voice_my.wav").exists()
    assert (pack_root / "subs" / "my.srt").exists()
    assert (pack_root / "scenes" / "scene_001.mp4").exists()
    assert (pack_root / "manifest.json").exists()
    assert (pack_root / "README.md").exists()

    manifest = json.loads((pack_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "1.7"
    assert manifest["pack_type"] == "youcut_ready"
    assert manifest["task_id"] == task_id
    assert manifest["language"] == "my"
    assert manifest["assets"] == {
        "raw_video": "raw/raw.mp4",
        "voice": "audio/voice_my.wav",
        "subtitle": "subs/my.srt",
        "scenes_dir": "scenes/",
    }
