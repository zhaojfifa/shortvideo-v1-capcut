from __future__ import annotations

import json
from pathlib import Path


def _write_placeholder_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(b"")


def generate_youcut_pack(task_id: str, out_root: Path, placeholders: bool = True) -> Path:
    out_root = Path(out_root)
    pack_root = out_root / task_id

    raw_path = pack_root / "raw" / "raw.mp4"
    audio_path = pack_root / "audio" / "voice_my.wav"
    subs_path = pack_root / "subs" / "my.srt"
    scenes_path = pack_root / "scenes" / "scene_001.mp4"

    pack_root.mkdir(parents=True, exist_ok=True)
    (pack_root / "raw").mkdir(parents=True, exist_ok=True)
    (pack_root / "audio").mkdir(parents=True, exist_ok=True)
    (pack_root / "subs").mkdir(parents=True, exist_ok=True)
    (pack_root / "scenes").mkdir(parents=True, exist_ok=True)

    if placeholders:
        _write_placeholder_file(raw_path)
        _write_placeholder_file(audio_path)
        _write_placeholder_file(scenes_path)
        subs_path.write_text(
            "1\n00:00:00,000 --> 00:00:02,000\n(placeholder)\n",
            encoding="utf-8",
        )

    manifest = {
        "version": "1.7",
        "pack_type": "youcut_ready",
        "task_id": task_id,
        "language": "my",
        "assets": {
            "raw_video": "raw/raw.mp4",
            "voice": "audio/voice_my.wav",
            "subtitle": "subs/my.srt",
            "scenes_dir": "scenes/",
        },
    }
    (pack_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )

    readme_text = (
        "YouCut import steps:\n"
        "1) Import raw/raw.mp4\n"
        "2) Import audio/voice_my.wav\n"
        "3) Import subs/my.srt\n"
        "\n"
        "Do not rename files/folders.\n"
        "Keep the directory structure.\n"
    )
    (pack_root / "README.md").write_text(readme_text, encoding="utf-8")

    return pack_root
