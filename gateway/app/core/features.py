from __future__ import annotations

import os


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def get_features() -> dict[str, bool]:
    return {
        "pack_download": _parse_bool(os.getenv("FEATURE_PACK_DOWNLOAD"), True),
        "asset_download": _parse_bool(os.getenv("FEATURE_ASSET_DOWNLOAD"), True),
        "publish_backfill": _parse_bool(os.getenv("FEATURE_PUBLISH_BACKFILL"), False),
    }
