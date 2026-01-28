from __future__ import annotations

from typing import Dict
from starlette.requests import Request

from gateway.app.i18n import get_ui_locale, t
from gateway.app.web.i18n import i18n_payload, t_for_locale, ui_langs


def get_template_globals(request: Request) -> Dict[str, object]:
    locale = get_ui_locale(request)
    t_func = t_for_locale(locale)
    return {
        "t": t_func,
        "t_primary": t_func,
        "t_secondary": lambda _key, **_kwargs: "",
        "ui_locale": locale,
        "i18n_payload": i18n_payload(locale),
        "ui_langs": ui_langs(locale),
    }
