from __future__ import annotations

from typing import Any, Dict

from gateway.app.config import get_settings
from gateway.app.db import engine, get_provider_config_map
from gateway.app.services.steps_v1 import (
    run_dub_step,
    run_pack_step,
    run_parse_step,
    run_subtitles_step,
)

AVAILABLE_PROVIDERS: Dict[str, list[str]] = {
    "parse": ["xiongmao", "xiaomao"],
    "subtitles": ["gemini", "whisper"],
    "dub": ["lovo", "edge-tts"],
    "pack": ["capcut", "youcut"],
    "face_swap": ["none", "xxx_faceswap_api"],
}


def default_providers(settings=None) -> Dict[str, str]:
    _settings = settings or get_settings()
    return {
        "parse": "xiongmao",
        "subtitles": "gemini",
        "dub": "lovo",
        "pack": "capcut",
        "face_swap": "none",
    }


def resolve_tool_providers(db_engine=engine, settings=None) -> Dict[str, Any]:
    defaults = default_providers(settings)
    stored = get_provider_config_map(db_engine)
    tools: Dict[str, Dict[str, Any]] = {}
    for tool, available in AVAILABLE_PROVIDERS.items():
        provider_key = f"{tool}_provider"
        enabled_key = f"{tool}_enabled"
        provider = stored.get(provider_key, defaults[tool])
        enabled_raw = stored.get(enabled_key)
        if enabled_raw is None:
            enabled = tool != "face_swap"
        else:
            enabled = str(enabled_raw).lower() in {"1", "true", "yes", "on"}
        tools[tool] = {
            "provider": provider,
            "enabled": enabled,
            "available": available,
        }
    return {"tools": tools}


def get_provider(tool_type: str, name: str):
    providers = {
        "parse": {
            "xiongmao": run_parse_step,
            "xiaomao": run_parse_step,
        },
        "subtitles": {
            "gemini": run_subtitles_step,
            "whisper": run_subtitles_step,
        },
        "dub": {
            "lovo": run_dub_step,
            "edge-tts": run_dub_step,
        },
        "pack": {
            "capcut": run_pack_step,
            "youcut": run_pack_step,
        },
    }
    tool_map = providers.get(tool_type, {})
    if name not in tool_map:
        raise KeyError(f"Unknown provider: {tool_type}:{name}")
    return tool_map[name]
