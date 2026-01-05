from __future__ import annotations

from typing import Callable, Dict

from gateway.app.web.i18n import SHOW_BILINGUAL, SECONDARY_UI_LANG, PRIMARY_UI_LANG
from gateway.app.web.i18n import I18N, bi, t_primary, t_secondary


def get_template_globals() -> Dict[str, object]:
    return {
        "t_primary": t_primary,
        "t_secondary": t_secondary,
        "bi": bi,
        "ui_primary_lang": PRIMARY_UI_LANG,
        "ui_secondary_lang": SECONDARY_UI_LANG,
        "ui_show_secondary": SHOW_BILINGUAL,
        "ui_bilingual": SHOW_BILINGUAL,
        "ui_langs": {
            "primary": PRIMARY_UI_LANG,
            "secondary": SECONDARY_UI_LANG,
            "secondary_enabled": SHOW_BILINGUAL,
            "available": list(I18N.keys()),
        },
    }
