from __future__ import annotations

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

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
