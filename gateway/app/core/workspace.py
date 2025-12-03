from pathlib import Path

from gateway.app.config import get_settings


def workspace_root() -> Path:
    return Path(get_settings().workspace_root).resolve()


def raw_path(task_id: str) -> Path:
    path = workspace_root() / "raw" / f"{task_id}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def subs_dir() -> Path:
    path = workspace_root() / "edits" / "subs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def audio_dir() -> Path:
    path = workspace_root() / "edits" / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def packs_dir() -> Path:
    path = workspace_root() / "packs"
    path.mkdir(parents=True, exist_ok=True)
    return path
