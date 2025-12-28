from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional


def _ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def _write_text(p: Path, content: str) -> None:
    _ensure_parent(p)
    p.write_text(content, encoding="utf-8")


def _touch(p: Path) -> None:
    _ensure_parent(p)
    if not p.exists():
        p.write_bytes(b"")


def generate_youcut_pack(task_id: str, out_root: Path, placeholders: bool = True) -> Path:
    """
    Create frozen v1.7 YouCut-ready pack skeleton.
    Returns the pack root path: out_root/task_id
    """
    pack_root = (out_root / task_id).resolve()
    (pack_root / "raw").mkdir(parents=True, exist_ok=True)
    (pack_root / "audio").mkdir(parents=True, exist_ok=True)
    (pack_root / "subs").mkdir(parents=True, exist_ok=True)
    (pack_root / "scenes").mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, Any] = {
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

    _write_text(pack_root / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    readme = (
        "# Smart Pack v1.7 (YouCut Ready)\n\n"
        "1. 打开 YouCut\n"
        "2. 导入 raw/raw.mp4\n"
        "3. 导入 audio/voice_my.wav\n"
        "4. 导入 subs/my.srt\n"
        "5. 按时间轴对齐字幕与配音\n\n"
        "注意：\n"
        "- 请勿修改文件名或目录结构\n"
    )
    _write_text(pack_root / "README.md", readme)

    if placeholders:
        _touch(pack_root / "raw" / "raw.mp4")
        _touch(pack_root / "audio" / "voice_my.wav")
        _write_text(
            pack_root / "subs" / "my.srt",
            "1\n00:00:00,000 --> 00:00:02,000\n(placeholder)\n",
        )
        _touch(pack_root / "scenes" / "scene_001.mp4")

    return pack_root


def zip_youcut_pack(pack_root: Path, zip_path: Optional[Path] = None) -> Path:
    """
    Zip the entire pack_root into {out_root}/{task_id}.zip by default.
    Zip internal structure is prefixed with task_id/...
    """
    pack_root = pack_root.resolve()
    task_id = pack_root.name
    if zip_path is None:
        zip_path = pack_root.parent / f"{task_id}.zip"

    zip_path = zip_path.resolve()
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    # Create zip with relative paths: task_id/...
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in pack_root.rglob("*"):
            if p.is_dir():
                continue
            rel_inside_pack = p.relative_to(pack_root)
            arcname = Path(task_id) / rel_inside_pack
            zf.write(p, arcname.as_posix())

    return zip_path
