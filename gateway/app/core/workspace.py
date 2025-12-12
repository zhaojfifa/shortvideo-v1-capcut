import json
from pathlib import Path

from gateway.app.config import get_settings


class Workspace:
    """Workspace helper for resolving per-task subtitle artifacts."""

    def __init__(self, task_id: str):
        self.task_id = task_id

    @property
    def base_dir(self) -> Path:
        return workspace_root()

    # Paths
    @property
    def raw(self) -> Path:
        return raw_path(self.task_id)

    @property
    def raw_video_path(self) -> Path:
        return self.raw

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

    def read_mm_srt_text(self) -> str | None:
        path = self.mm_srt_path
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    @property
    def subtitles_dir(self) -> Path:
        return subs_dir()

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

    # Audio helpers
    @property
    def mm_audio_primary_path(self) -> Path:
        return audio_dir() / f"{self.task_id}_mm.wav"

    @property
    def mm_audio_legacy_path(self) -> Path:
        return dubbed_audio_path(self.task_id)

    @property
    def mm_audio_path(self) -> Path:
        primary = self.mm_audio_primary_path
        if primary.exists():
            return primary
        return self.mm_audio_legacy_path

    def mm_audio_exists(self) -> bool:
        return self.mm_audio_primary_path.exists() or self.mm_audio_legacy_path.exists()

    def write_mm_audio(self, content: bytes, suffix: str = "wav") -> Path:
        audio_dir().mkdir(parents=True, exist_ok=True)
        suffix = suffix.lstrip(".") or "wav"
        path = audio_dir() / f"{self.task_id}_mm.{suffix}"
        path.write_bytes(content)
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
    path = workspace_root() / "raw" / f"{task_id}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def subs_dir() -> Path:
    path = workspace_root() / "edits" / "subs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def scenes_dir() -> Path:
    path = workspace_root() / "edits" / "scenes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def scenes_json_path(task_id: str) -> Path:
    path = scenes_dir() / f"{task_id}_scenes.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def segments_json_path(task_id: str) -> Path:
    path = scenes_dir() / f"{task_id}_segments.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def audio_dir() -> Path:
    path = workspace_root() / "edits" / "audio"
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


def packs_dir() -> Path:
    path = workspace_root() / "packs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def tmp_dir() -> Path:
    path = workspace_root() / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def audio_wav_path(task_id: str) -> Path:
    path = subs_dir() / f"{task_id}.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def origin_srt_path(task_id: str) -> Path:
    path = subs_dir() / f"{task_id}_origin.srt"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def translated_srt_path(task_id: str, target_lang: str) -> Path:
    suffix = target_lang or "mm"
    path = subs_dir() / f"{task_id}_{suffix}.srt"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def dubbed_audio_path(task_id: str) -> Path:
    path = audio_dir() / f"{task_id}_mm_vo.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def pack_zip_path(task_id: str) -> Path:
    path = packs_dir() / f"{task_id}_capcut_pack.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def relative_to_workspace(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace_root()))
    except ValueError:
        return str(path)
