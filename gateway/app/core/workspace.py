from pathlib import Path

from gateway.app.config import get_settings


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
