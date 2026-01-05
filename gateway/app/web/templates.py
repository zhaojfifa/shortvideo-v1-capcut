from __future__ import annotations

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from gateway.app.web.i18n import bi, t_primary, t_secondary, ui_langs
from gateway.app.web.template_helpers import get_template_globals

templates = Jinja2Templates(directory="gateway/app/templates")
templates.env.globals["t_primary"] = t_primary
templates.env.globals["t_secondary"] = t_secondary
templates.env.globals["bi"] = bi
templates.env.globals["ui_langs"] = ui_langs


def _template_context(_: Request) -> dict[str, object]:
    """Compute template globals per-request to avoid shared state drifting."""
    return get_template_globals()


# Use a context processor so globals refresh per request (env globals are shared
# across requests and can become stale if settings or language preferences
# change at runtime).
templates.context_processors.append(_template_context)


def get_templates() -> Jinja2Templates:
    """
    Backward-compatible accessor for routes that import get_templates().
    Prefer importing `templates` directly in new code.
    """
    return templates
