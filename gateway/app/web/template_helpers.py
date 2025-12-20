from __future__ import annotations

from typing import Callable, Dict

from gateway.app.config import get_settings
from gateway.app.i18n import TRANSLATIONS


def _t(lang: str) -> Callable[[str], str]:
    table = TRANSLATIONS.get(lang, {})

    def tr(key: str) -> str:
        return table.get(key, key)

    return tr


def get_template_globals() -> Dict[str, object]:
    settings = get_settings()
    primary = settings.ui_primary_lang or "zh"
    secondary = settings.ui_secondary_lang or "my"
    return {
        "t_primary": _t(primary),
        "t_secondary": _t(secondary),
        "ui_primary_lang": primary,
        "ui_secondary_lang": secondary,
        "ui_show_secondary": settings.ui_show_secondary,
    }
