import json
import shutil
from pathlib import Path

from gateway.app.config import get_settings


def task_base_dir(task_id: str) -> Path:
    """Return the base directory for a specific task under workspace_root/tasks/<task_id>."""

    base = workspace_root() / "tasks" / task_id
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_task_workspace(task_id: str) -> dict[str, Path]:
    """Materialize and return common per-task workspace paths."""

    base = task_base_dir(task_id)
    paths = {
        "base": base,
        "raw": base / "raw",
        "subs": base / "subs",
        "audio": base / "audio",
        "pack": base / "pack",
    }

    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)

    return paths


class Workspace:
    """Workspace helper for resolving per-task subtitle artifacts."""

    def __init__(self, task_id: str):
        self.task_id = task_id

    @property
    def base_dir(self) -> Path:
        return task_base_dir(self.task_id)

    # Paths
    @property
    def raw(self) -> Path:
        return raw_path(self.task_id)

    @property
    def raw_video_path(self) -> Path:
        return self.raw

    @property
    def raw_input_path(self) -> Path:
        return raw_input_path(self.task_id)

    def raw_video_exists(self) -> bool:
        return self.raw_video_path.exists()

    @property
    def origin_srt(self) -> Path:
        return origin_srt_path(self.task_id)

    @property
    def origin_srt_path(self) -> Path:
        return origin_srt_path(self.task_id)

    @property
    def mm_srt(self) -> Path:
        return self.mm_srt_path

    @property
    def mm_srt_path(self) -> Path:
        """Canonical path for translated (Burmese) subtitles.

        Historically stored via translated_srt_path; prefer the mm suffix but
        fall back to my for backward compatibility.
        """

        primary = translated_srt_path(self.task_id, "mm")
        alternate = translated_srt_path(self.task_id, "my")

        if not primary.exists() and alternate.exists():
            return alternate

        return primary

    def mm_srt_exists(self) -> bool:
        primary = translated_srt_path(self.task_id, "mm")
        alternate = translated_srt_path(self.task_id, "my")
        return primary.exists() or alternate.exists()

    @property
    def mm_txt_path(self) -> Path:
        return self.mm_srt_path.with_suffix(".txt")

    def read_mm_srt_text(self) -> str | None:
        path = self.mm_srt_path
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    @property
    def subtitles_dir(self) -> Path:
        return subs_dir(self.task_id)

    @property
    def segments_json(self) -> Path:
        return segments_json_path(self.task_id)

    @property
    def scenes_json(self) -> Path:
        return scenes_json_path(self.task_id)

    # IO helpers
    def read_origin_srt_text(self) -> str | None:
        if not self.origin_srt_path.exists():
            return None
        return self.origin_srt_path.read_text(encoding="utf-8")

    def write_origin_srt(self, text: str) -> Path:
        self.subtitles_dir.mkdir(parents=True, exist_ok=True)
        self.origin_srt_path.write_text(text, encoding="utf-8")
        return self.origin_srt_path

    def write_mm_srt(self, text: str) -> Path:
        self.subtitles_dir.mkdir(parents=True, exist_ok=True)
        path = translated_srt_path(self.task_id, "mm")
        path.write_text(text, encoding="utf-8")
        return path

    def read_mm_edited_text(self) -> str | None:
        path = self.base_dir / "mm_edited.txt"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    # Audio helpers
    @property
    def mm_audio_primary_path(self) -> Path:
        return audio_dir(self.task_id) / f"{self.task_id}_mm.wav"

    @property
    def mm_audio_mp3_path(self) -> Path:
        return audio_dir(self.task_id) / f"{self.task_id}_mm.mp3"

    @property
    def mm_audio_legacy_path(self) -> Path:
        return dubbed_audio_path(self.task_id)

    @property
    def mm_audio_path(self) -> Path:
        primary = self.mm_audio_primary_path
        mp3_path = self.mm_audio_mp3_path
        if primary.exists():
            return primary
        if mp3_path.exists():
            return mp3_path
        return self.mm_audio_legacy_path

    def mm_audio_exists(self) -> bool:
        return (
            self.mm_audio_primary_path.exists()
            or self.mm_audio_mp3_path.exists()
            or self.mm_audio_legacy_path.exists()
        )

    def write_mm_audio(self, content: bytes, suffix: str = "wav") -> Path:
        audio_dir(self.task_id).mkdir(parents=True, exist_ok=True)
        suffix = suffix.lstrip(".") or "wav"
        path = audio_dir(self.task_id) / f"{self.task_id}_mm.{suffix}"
        path.write_bytes(content)
        ensure_public_audio(path)
        return path

    def mm_audio_media_type(self) -> str:
        ext = self.mm_audio_path.suffix.lower()
        if ext == ".mp3":
            return "audio/mpeg"
        return "audio/wav"

    def write_segments_json(self, data: dict) -> None:
        self.segments_json.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # scenes 文件用于向后兼容（如果下游读取该名称）。
        scenes = {"scenes": data.get("scenes", [])}
        self.scenes_json.write_text(
            json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def workspace_root() -> Path:
    root = Path(get_settings().workspace_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def raw_path(task_id: str) -> Path:
    path = task_base_dir(task_id) / "raw" / "raw.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def raw_clean_path(task_id: str) -> Path:
    path = task_base_dir(task_id) / "raw" / "raw_clean.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def raw_input_path(task_id: str) -> Path:
    clean = raw_clean_path(task_id)
    if clean.exists():
        return clean
    return raw_path(task_id)


def subs_dir(task_id: str) -> Path:
    path = task_base_dir(task_id) / "subs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def scenes_json_path(task_id: str) -> Path:
    path = subs_dir(task_id) / f"{task_id}_scenes.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def segments_json_path(task_id: str) -> Path:
    path = subs_dir(task_id) / f"{task_id}_segments.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def audio_dir(task_id: str) -> Path:
    path = task_base_dir(task_id) / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def deliver_dir() -> Path:
    path = workspace_root() / "deliver"
    path.mkdir(parents=True, exist_ok=True)
    return path


def assets_dir() -> Path:
    path = workspace_root() / "assets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def public_audio_dir() -> Path:
    path = workspace_root() / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_public_audio(path: Path) -> Path:
    target = public_audio_dir() / path.name
    if path.exists() and not target.exists():
        shutil.copy2(path, target)
    return target


def packs_dir(task_id: str) -> Path:
    path = task_base_dir(task_id) / "pack"
    path.mkdir(parents=True, exist_ok=True)
    return path


def tmp_dir() -> Path:
    path = workspace_root() / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def audio_wav_path(task_id: str) -> Path:
    path = subs_dir(task_id) / f"{task_id}.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def origin_srt_path(task_id: str) -> Path:
    path = subs_dir(task_id) / "origin.srt"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def translated_srt_path(task_id: str, target_lang: str) -> Path:
    suffix = target_lang or "mm"
    path = subs_dir(task_id) / f"{suffix}.srt"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def dubbed_audio_path(task_id: str) -> Path:
    path = audio_dir(task_id) / f"{task_id}_mm_vo.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def pack_zip_path(task_id: str) -> Path:
    path = packs_dir(task_id) / f"{task_id}_capcut_pack.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def deliver_pack_zip_path(task_id: str) -> Path:
    path = workspace_root() / "deliver" / "packs" / task_id / "capcut_pack.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def relative_to_workspace(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace_root()))
    except ValueError:
        return str(path)


def relative_to_task_workspace(path: Path, task_id: str) -> str:
    try:
        return str(path.resolve().relative_to(task_base_dir(task_id)))
    except ValueError:
        return str(path)
