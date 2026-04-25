"""Generic background worker for long-running core tasks."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal, Slot


class TaskWorker(QObject):
    """Run a synchronous callable on a QThread and emit structured results."""

    finished = Signal(object)
    failed = Signal(Exception)

    def __init__(self, runner: Callable[[], object]) -> None:
        super().__init__()
        self._runner = runner

    @Slot()
    def run(self) -> None:
        try:
            result = self._runner()
        except Exception as exc:
            self.failed.emit(exc)
            return
        self.finished.emit(result)
