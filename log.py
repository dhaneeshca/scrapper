"""
Central logging setup. Call setup() once at process start.
Writes to both stdout and log.txt (appended).

Each scrape run sets a short run_id via set_run_id(); every log line in that
thread/coroutine automatically gets a [xxxxxxxx] prefix so you can grep a
single run in log.txt.
"""
import logging
import os
import uuid
from contextvars import ContextVar

LOG_FILE = os.path.join(os.path.dirname(__file__), "log.txt")

_run_id_var: ContextVar[str] = ContextVar("run_id", default="-" * 8)


def new_run_id() -> str:
    """Generate and activate a new run ID for the current context. Returns it."""
    rid = uuid.uuid4().hex[:8]
    _run_id_var.set(rid)
    return rid


class _RunIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = _run_id_var.get()
        return True


def setup() -> None:
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  [%(run_id)s]  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    run_filter = _RunIdFilter()

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.addFilter(run_filter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    console_handler.addFilter(run_filter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console_handler)


# Uvicorn log_config dict — keeps uvicorn's access + error logs in the same file
UVICORN_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "run_id": {"()": "log._RunIdFilter"},
    },
    "formatters": {
        "default": {
            "()": "logging.Formatter",
            "fmt": "%(asctime)s  %(levelname)-8s  [%(run_id)s]  %(name)s  %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "filters": ["run_id"],
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.FileHandler",
            "formatter": "default",
            "filters": ["run_id"],
            "filename": LOG_FILE,
            "encoding": "utf-8",
            "mode": "a",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["console", "file"], "level": "INFO", "propagate": False},
    },
}
