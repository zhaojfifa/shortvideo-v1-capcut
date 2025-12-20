from __future__ import annotations

from functools import lru_cache

from fastapi.templating import Jinja2Templates

from gateway.app.config import get_settings
from gateway.app.i18n import t_bi, t_primary, t_secondary


@lru_cache()
def get_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory="gateway/app/templates")
    settings = get_settings()
    templates.env.globals["t_primary"] = t_primary
    templates.env.globals["t_secondary"] = t_secondary
    templates.env.globals["t_bi"] = t_bi
    templates.env.globals["ui_primary_lang"] = settings.ui_primary_lang
    templates.env.globals["ui_secondary_lang"] = settings.ui_secondary_lang
    templates.env.globals["ui_show_secondary"] = settings.ui_show_secondary
    templates.env.globals["ui_mobile_prefix_enabled"] = settings.ui_mobile_prefix_enabled
    return templates
