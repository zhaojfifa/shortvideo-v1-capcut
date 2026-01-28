from __future__ import annotations

from typing import Any, Dict

from gateway.app.i18n import (
    I18N_DICT,
    STRICT_OPERATOR_LOCALE,
    SUPPORTED_UI_LOCALES,
    build_i18n_payload,
    get_ui_locale,
    t,
)


def t_for_locale(locale: str):
    def _t(key: str, **kwargs: Any) -> str:
        return t(key, locale, **kwargs)

    return _t


def i18n_payload(locale: str) -> Dict[str, object]:
    return build_i18n_payload(locale)


def ui_langs(locale: str) -> Dict[str, object]:
    return {
        "current": locale,
        "supported": SUPPORTED_UI_LOCALES,
        "strict": STRICT_OPERATOR_LOCALE,
        "available": list(I18N_DICT.keys()),
    }
