"""Logging configuration for both console and rotating file.

Call :func:`configure_logging` once at process start. Subsequent calls are
idempotent — handlers are only attached the first time.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from archivestudio.core.config.paths import PathAccessError, user_log_file
from archivestudio.core.errors import redact_secrets

_CONFIGURED = False

_DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class RedactingFormatter(logging.Formatter):
    """Formatter that removes common API key shapes from all log output."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_secrets(super().format(record))


def configure_logging(
    level: int = logging.INFO,
    *,
    log_file: Path | None = None,
    max_bytes: int = 2_000_000,
    backup_count: int = 5,
) -> None:
    """Attach a console handler and a rotating file handler to the root logger.

    Safe to call repeatedly; only configures once.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(level)

    formatter = RedactingFormatter(_DEFAULT_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(level)
    root.addHandler(console)

    target = log_file if log_file is not None else user_log_file()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            target,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
    except (OSError, PathAccessError) as exc:
        root.warning("Could not create ArchiveStudio log file at %s: %s", target, exc)
    else:
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root.addHandler(file_handler)

    # Quiet noisy third-party loggers by default.
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _CONFIGURED = True
    logging.getLogger(__name__).debug("Logging configured; file=%s", target)
