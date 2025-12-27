"""
Compatibility shim for legacy imports: gateway.app.services.dubbing

IMPORTANT:
- Do NOT implement dubbing logic here.
- Route to v1.62+ step/usecase that reads subtitles.json (SSOT).
"""

from __future__ import annotations

import importlib
from typing import Any, Callable, Optional


class DubbingError(RuntimeError):
    """Raised when dubbing synthesis fails."""


def _resolve_callable() -> Callable[..., Any]:
    """
    Try to find the real dubbing entrypoint in the refactored codebase.
    We intentionally support multiple candidates to avoid tight coupling.
    """
    candidates = [
        # Most likely: steps layer
        ("gateway.app.steps.dub", "run_dub_step"),
        ("gateway.app.steps.dubbing", "run_dub_step"),
        ("gateway.app.steps.dub", "synthesize_voice"),
        ("gateway.app.steps.dubbing", "synthesize_voice"),

        # Alternative: usecase/application layer naming
        ("gateway.app.usecases.dub", "run_dub_step"),
        ("gateway.app.usecases.dubbing", "run_dub_step"),
        ("gateway.app.usecases.dub", "synthesize_voice"),
        ("gateway.app.usecases.dubbing", "synthesize_voice"),

        # Sometimes people put it under services/steps_v1 during migration
        ("gateway.app.steps_v1.dub", "run_dub_step"),
        ("gateway.app.steps_v1.dubbing", "run_dub_step"),
    ]

    last_err: Optional[Exception] = None
    for mod_name, attr in candidates:
        try:
            mod = importlib.import_module(mod_name)
            fn = getattr(mod, attr, None)
            if callable(fn):
                return fn  # type: ignore[return-value]
        except Exception as e:
            last_err = e

    raise ImportError(
        "Cannot resolve dubbing entrypoint. "
        "Expected run_dub_step/synthesize_voice in one of: "
        + ", ".join([f"{m}.{a}" for m, a in candidates])
        + (f". Last error: {last_err}" if last_err else "")
    )


def synthesize_voice(*args: Any, **kwargs: Any) -> Any:
    """
    Legacy API surface preserved.
    Delegates to v1.62+ step/usecase implementation.
    """
    try:
        fn = _resolve_callable()
        return fn(*args, **kwargs)
    except Exception as e:
        # keep a stable error type for callers
        raise DubbingError(str(e)) from e


__all__ = ["DubbingError", "synthesize_voice"]
