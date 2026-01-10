import logging
import os


class SafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        for key in ("task_id", "step", "phase", "provider", "elapsed_ms"):
            if key not in record.__dict__:
                record.__dict__[key] = "-"
        return super().format(record)


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    if not root.handlers:
        fmt = (
            "%(levelname)s %(name)s "
            "task=%(task_id)s step=%(step)s phase=%(phase)s "
            "provider=%(provider)s elapsed_ms=%(elapsed_ms)s "
            "%(message)s"
        )
        handler = logging.StreamHandler()
        handler.setFormatter(SafeFormatter(fmt))
        logging.basicConfig(level=level, handlers=[handler])

    root.setLevel(level)
    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(level)
