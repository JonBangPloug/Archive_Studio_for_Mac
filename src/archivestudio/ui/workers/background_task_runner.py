"""QThread orchestration for long-running UI background tasks."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal

from archivestudio.ui.workers.task_worker import TaskWorker


class BackgroundTaskRunner(QObject):
    """Own the lifetime and signal wiring for one background task at a time."""

    finished = Signal(object)
    failed = Signal(Exception)
    progress = Signal(object)
    running_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._active_thread: QThread | None = None
        self._active_worker: TaskWorker | None = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self, runner: Callable[[], object]) -> None:
        """Start ``runner`` on a QThread.

        ``BackgroundTaskRunner`` intentionally supports only one active task.
        Callers should disable task-starting UI while ``is_running`` is true.
        """
        if self._is_running:
            raise RuntimeError("A background task is already running.")

        worker = TaskWorker(runner)
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self.finished.emit)
        worker.failed.connect(self.failed.emit)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_references)

        self._active_thread = thread
        self._active_worker = worker
        self._set_running(True)
        thread.start()

    def report_progress(self, progress: object) -> None:
        """Forward worker-thread progress updates to the UI thread."""
        self.progress.emit(progress)

    def _clear_references(self) -> None:
        self._active_thread = None
        self._active_worker = None
        self._set_running(False)

    def _set_running(self, is_running: bool) -> None:
        if self._is_running == is_running:
            return
        self._is_running = is_running
        self.running_changed.emit(is_running)
