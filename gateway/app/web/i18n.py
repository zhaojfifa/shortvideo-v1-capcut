from __future__ import annotations

from typing import Any, Dict

from gateway.app.i18n import (
    build_i18n_payload,
    get_supported_locales,
    get_translator,
)


def t_for_locale(locale: str):
    return get_translator(locale)


def i18n_payload(locale: str) -> Dict[str, object]:
    return build_i18n_payload(locale)


def ui_langs(locale: str) -> Dict[str, object]:
    return {
        "current": locale,
        "supported": get_supported_locales(),
    }
