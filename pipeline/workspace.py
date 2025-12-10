from pathlib import Path

from pipeline import config


def workspace_root() -> Path:
    return config.WORKSPACE_ROOT


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def raw_path(task_id: str) -> Path:
    path = workspace_root() / "raw" / f"{task_id}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def subs_dir() -> Path:
    return ensure_dir(workspace_root() / "edits" / "subs")


def scenes_dir() -> Path:
    return ensure_dir(workspace_root() / "edits" / "scenes")


def audio_dir() -> Path:
    return ensure_dir(workspace_root() / "edits" / "audio")


def packs_dir() -> Path:
    return ensure_dir(workspace_root() / "packs")


def deliver_dir() -> Path:
    return ensure_dir(workspace_root() / "deliver")


def assets_dir() -> Path:
    return ensure_dir(workspace_root() / "assets")
