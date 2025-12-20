import json
from pathlib import Path
from typing import Dict

from gateway.app.config import get_settings


DEFAULTS: Dict[str, str] = {
    "parse": "xiongmao",
    "subtitles": "gemini",
    "dub": "lovo",
    "pack": "capcut",
    "face_swap": "none",
}


def _config_path() -> Path:
    settings = get_settings()
    root = Path(settings.workspace_root).expanduser().resolve()
    return root / "config" / "tools.json"


def get_defaults() -> Dict[str, str]:
    path = _config_path()
    if not path.exists():
        return DEFAULTS.copy()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return DEFAULTS.copy()
    if not isinstance(data, dict):
        return DEFAULTS.copy()
    merged = DEFAULTS.copy()
    for key, value in data.items():
        if key in DEFAULTS and isinstance(value, str):
            merged[key] = value
    return merged


def save_defaults(payload: Dict[str, str]) -> Dict[str, str]:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = DEFAULTS.copy()
    for key, value in payload.items():
        if key in DEFAULTS and isinstance(value, str):
            data[key] = value
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
