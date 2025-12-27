from __future__ import annotations

from typing import Callable, Dict

from gateway.app.web.i18n import ENABLE_SECONDARY_UI, SECONDARY_UI_LANG, PRIMARY_UI_LANG
from gateway.app.web.i18n import I18N, t_primary, t_secondary


def get_template_globals() -> Dict[str, object]:
    return {
        "t_primary": t_primary,
        "t_secondary": t_secondary,
        "ui_primary_lang": PRIMARY_UI_LANG,
        "ui_secondary_lang": SECONDARY_UI_LANG,
        "ui_show_secondary": ENABLE_SECONDARY_UI,
        "ui_langs": {
            "primary": PRIMARY_UI_LANG,
            "secondary": SECONDARY_UI_LANG,
            "secondary_enabled": ENABLE_SECONDARY_UI,
            "available": list(I18N.keys()),
        },
    }
