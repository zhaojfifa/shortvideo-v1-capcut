from __future__ import annotations

from typing import Any, Dict, Optional

from starlette.requests import Request
from starlette.templating import Jinja2Templates

from gateway.app.web.template_helpers import get_template_globals

templates = Jinja2Templates(directory="gateway/app/templates")


def _template_context(request: Request) -> dict[str, object]:
    """Compute template globals per-request to avoid shared state drifting."""
    return get_template_globals(request)


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


def render_template(*, request: Request, name: str, ctx: Optional[Dict[str, Any]] = None):
    """
    Render a template with per-request i18n globals injected.
    """
    data: Dict[str, Any] = {"request": request}
    if ctx:
        data.update(ctx)
    data.update(get_template_globals(request))
    return templates.TemplateResponse(name, data)
