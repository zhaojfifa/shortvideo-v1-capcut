import json
from pathlib import Path
from typing import Any, Dict

from gateway.app.config import get_settings


DEFAULTS: Dict[str, Dict[str, Any]] = {
    "parse": {"provider": "xiaomao", "enabled": True},
    "subtitles": {"provider": "gemini", "enabled": True},
    "dub": {"provider": "lovo", "enabled": True},
    "pack": {"provider": "capcut", "enabled": True},
    "face_swap": {"provider": "none", "enabled": False},
}


def _config_path() -> Path:
    settings = get_settings()
    root = Path(settings.workspace_root).expanduser().resolve()
    return root / "config" / "tools.json"


def _merge_defaults(payload: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for key, value in DEFAULTS.items():
        merged[key] = dict(value)
    for key, value in (payload or {}).items():
        if key in DEFAULTS and isinstance(value, dict):
            provider = value.get("provider")
            enabled = value.get("enabled")
            if isinstance(provider, str):
                merged[key]["provider"] = provider
            if isinstance(enabled, bool):
                merged[key]["enabled"] = enabled
        elif key not in DEFAULTS:
            merged[key] = value
    return merged


def get_defaults() -> Dict[str, Any]:
    path = _config_path()
    if not path.exists():
        return _merge_defaults({})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _merge_defaults({})
    if not isinstance(data, dict):
        return _merge_defaults({})
    return _merge_defaults(data)


def save_defaults(payload: Dict[str, Any]) -> Dict[str, Any]:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[str, Any] = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = raw
        except json.JSONDecodeError:
            existing = {}
    merged = _merge_defaults(existing)
    if payload:
        merged = _merge_defaults({**merged, **payload})
    data = merged
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def get_defaults_structured() -> Dict[str, Any]:
    return get_defaults()


def save_defaults_structured(payload: Dict[str, Any]) -> Dict[str, Any]:
    return save_defaults(payload)
