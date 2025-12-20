from __future__ import annotations

from fastapi.templating import Jinja2Templates

from gateway.app.web.template_helpers import get_template_globals

templates = Jinja2Templates(directory="gateway/app/templates")
templates.env.globals.update(get_template_globals())


def get_templates() -> Jinja2Templates:
    """
    Backward-compatible accessor for routes that import get_templates().
    Prefer importing `templates` directly in new code.
    """
    return templates
