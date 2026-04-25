"""Background task runner tests."""

from __future__ import annotations

from PySide6.QtCore import QThread

import pytest

from archivestudio.ui.workers.background_task_runner import BackgroundTaskRunner


def test_background_task_runner_emits_finished(qtbot) -> None:
    runner = BackgroundTaskRunner()
    results: list[object] = []
    runner.finished.connect(results.append)

    with qtbot.waitSignal(
        runner.running_changed,
        timeout=1000,
        check_params_cb=lambda is_running: is_running is False,
    ):
        runner.start(lambda: "done")

    assert results == ["done"]
    assert runner.is_running is False


def test_background_task_runner_emits_failed(qtbot) -> None:
    runner = BackgroundTaskRunner()
    errors: list[Exception] = []
    runner.failed.connect(errors.append)

    def fail() -> object:
        raise ValueError("boom")

    with qtbot.waitSignal(
        runner.running_changed,
        timeout=1000,
        check_params_cb=lambda is_running: is_running is False,
    ):
        runner.start(fail)

    error = errors[0]
    assert isinstance(error, ValueError)
    assert str(error) == "boom"
    assert runner.is_running is False


def test_background_task_runner_rejects_overlapping_tasks(qtbot) -> None:
    runner = BackgroundTaskRunner()

    def slow() -> str:
        QThread.msleep(200)
        return "done"

    runner.start(slow)
    qtbot.waitUntil(lambda: runner.is_running, timeout=1000)

    with pytest.raises(RuntimeError, match="already running"):
        runner.start(lambda: "second")

    with qtbot.waitSignal(
        runner.running_changed,
        timeout=1000,
        check_params_cb=lambda is_running: is_running is False,
    ):
        pass
    assert runner.is_running is False
