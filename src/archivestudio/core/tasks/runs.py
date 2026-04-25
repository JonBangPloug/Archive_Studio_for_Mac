"""Shared task-run persistence helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import islice
from typing import Iterable, Iterator, Sequence, TypeVar

from archivestudio.core.models import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_PARTIAL,
    TASK_STATUS_RUNNING,
    TaskRun,
)
from archivestudio.core.project import Project


T = TypeVar("T")


@dataclass(frozen=True)
class TaskRunSummary:
    """Structured summary returned by task services."""

    task_run_id: str
    task_type: str
    preset_name: str
    pages_requested: int
    pages_completed: int
    pages_failed: int
    status: str
    created_text_version_ids: list[str]
    errors: list[str]


@dataclass(frozen=True)
class TaskProgress:
    """Incremental progress emitted by long-running task services."""

    task_type: str
    preset_name: str
    pages_total: int
    pages_completed: int
    pages_failed: int
    current_pages: tuple[int, ...] = ()
    message: str = ""

    @property
    def pages_processed(self) -> int:
        return self.pages_completed + self.pages_failed


ProgressCallback = Callable[[TaskProgress], None]


def emit_progress(callback: ProgressCallback | None, progress: TaskProgress) -> None:
    """Emit progress without letting UI callback failures break core tasks."""
    if callback is None:
        return
    try:
        callback(progress)
    except Exception:  # pragma: no cover - defensive isolation
        return


def create_task_run(
    project: Project,
    *,
    preset_name: str,
    task_type: str,
    model_id: str,
    pages_requested: int,
) -> str:
    with project.session() as session:
        task_run = TaskRun(
            preset_name=preset_name,
            task_type=task_type,
            model_id=model_id,
            status=TASK_STATUS_RUNNING,
            pages_requested=pages_requested,
        )
        session.add(task_run)
        session.flush()
        return task_run.id


def complete_task_run(
    project: Project,
    *,
    task_run_id: str,
    status: str,
    pages_completed: int,
    pages_failed: int,
    error_message: str | None,
) -> None:
    with project.session() as session:
        task_run = session.get(TaskRun, task_run_id)
        if task_run is None:  # pragma: no cover - defensive
            raise ValueError(f"Unknown task run: {task_run_id}")
        task_run.status = status
        task_run.completed_at = datetime.now(timezone.utc)
        task_run.pages_completed = pages_completed
        task_run.pages_failed = pages_failed
        task_run.error_message = error_message


def final_status(pages_completed: int, pages_failed: int) -> str:
    if pages_completed and not pages_failed:
        return TASK_STATUS_COMPLETED
    if pages_completed and pages_failed:
        return TASK_STATUS_PARTIAL
    return TASK_STATUS_FAILED


def chunked(values: Sequence[T], size: int) -> Iterator[list[T]]:
    iterator = iter(values)
    while batch := list(islice(iterator, size)):
        yield batch
