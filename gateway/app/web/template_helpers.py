from __future__ import annotations

from typing import Dict
from starlette.requests import Request

from gateway.app.i18n import get_supported_locales, get_translator, get_ui_locale
from gateway.app.web.i18n import i18n_payload


def get_template_globals(request: Request) -> Dict[str, object]:
    locale = get_ui_locale(request)
    t_func = get_translator(locale)
    return {
        "ui_locale": locale,
        "supported_locales": get_supported_locales(),
        "t": t_func,
        "i18n_payload": i18n_payload(locale),
    }
