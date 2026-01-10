import logging
import os
from typing import Optional

_CONFIGURED = False


class SafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        if "task" not in record.__dict__ and "task_id" in record.__dict__:
            record.__dict__["task"] = record.__dict__["task_id"]
        for key in ("task", "step", "phase", "provider", "elapsed_ms"):
            if key not in record.__dict__:
                record.__dict__[key] = "-"
        return super().format(record)


def configure_logging(level: Optional[str] = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    level_name = (
        level
        or os.getenv("APP_LOG_LEVEL")
        or os.getenv("UVICORN_LOG_LEVEL")
        or os.getenv("LOG_LEVEL")
        or "INFO"
    ).upper()
    resolved_level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    if not root.handlers:
        fmt = (
            "%(levelname)s %(name)s "
            "task=%(task)s step=%(step)s phase=%(phase)s "
            "provider=%(provider)s elapsed_ms=%(elapsed_ms)s "
            "%(message)s"
        )
        handler = logging.StreamHandler()
        handler.setFormatter(SafeFormatter(fmt))
        root.addHandler(handler)

    root.setLevel(resolved_level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.setLevel(resolved_level)
        logger.propagate = False

    _CONFIGURED = True
