"""Generic background worker for long-running core tasks."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal, Slot

from archivestudio.core.tasks.cancellation import CancellationToken, TaskCancelled


class TaskWorker(QObject):
    """Run a synchronous callable on a QThread and emit structured results."""

    finished = Signal(object)
    failed = Signal(Exception)
    cancelled = Signal(Exception)

    def __init__(
        self,
        runner: Callable[[], object],
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        super().__init__()
        self._runner = runner
        self._cancellation_token = cancellation_token or CancellationToken()

    def cancel(self) -> None:
        self._cancellation_token.cancel()

    @Slot()
    def run(self) -> None:
        try:
            result = self._runner()
        except TaskCancelled as exc:
            self.cancelled.emit(exc)
            return
        except Exception as exc:
            self.failed.emit(exc)
            return
        self.finished.emit(result)
