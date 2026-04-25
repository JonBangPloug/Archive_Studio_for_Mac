"""Application entry point.

Qt is imported lazily inside ``run`` so that the ``core`` package (and any CLI
or test harness that only needs the domain layer) can be imported without a
display server or PySide6 installed.
"""

from __future__ import annotations

import logging
import sys

from archivestudio import __display_name__, __version__
from archivestudio.core.config import PathAccessError, ensure_user_settings_file
from archivestudio.core.logging import configure_logging


log = logging.getLogger(__name__)


def run(argv: list[str] | None = None) -> int:
    """Launch the Qt application. Returns the process exit code."""
    configure_logging()
    try:
        settings_path = ensure_user_settings_file()
    except PathAccessError as exc:
        print(f"ArchiveStudio could not start: {exc}", file=sys.stderr)
        return 1
    log.info("ArchiveStudio v%s starting", __version__)
    log.info("Using user settings file at %s", settings_path)

    # Deferred import so core-only callers don't pay for Qt.
    from PySide6.QtWidgets import QApplication

    from archivestudio.ui.main_window import MainWindow

    app = QApplication(sys.argv if argv is None else argv)
    app.setApplicationName(__display_name__)
    app.setOrganizationName("ArchiveStudio")

    window = MainWindow()
    window.show()

    exit_code = app.exec()
    log.info("ArchiveStudio exiting with code %d", exit_code)
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(run())
