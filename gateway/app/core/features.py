from __future__ import annotations

import os
from typing import Dict


def _bool_env(name: str, default: str = "false") -> bool:
    """
    Parse env var into bool.
    True values: 1, true, yes, on (case-insensitive).
    """
    val = os.getenv(name, default)
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def get_features() -> Dict[str, bool]:
    """
    Operational feature flags (runtime toggles).
    Keep ALL flags centralized here to avoid scattered conditionals in templates/routers.
    """
    return {
        # Allow pack download link to appear in UI.
        # For CN "ops/admin" instances you may set FEATURE_ALLOW_PACK_DOWNLOAD=false.
        "allow_pack_download": _bool_env("FEATURE_ALLOW_PACK_DOWNLOAD", "true"),

        # Optional: show Admin Tools entry points (if you add nav later).
        "show_admin_tools": _bool_env("FEATURE_SHOW_ADMIN_TOOLS", "true"),

        # Optional: allow one-click auto pipeline (if you add in UI later).
        "enable_auto_pipeline": _bool_env("FEATURE_ENABLE_AUTO_PIPELINE", "true"),
    }
